"""Despliega AegisVolt en minikube (un namespace por ambiente), cuidando la RAM.

Uso (Floci arriba con `docker compose up -d`):
    uv run python scripts/deploy.py --env dev                       # build + todo
    uv run python scripts/deploy.py --env dev --tag v4              # versión nueva (CI: sha)
    uv run python scripts/deploy.py --env dev --skip-build          # solo manifiestos
    uv run python scripts/deploy.py --env dev --only graphql-gateway frontend   # demo liviana

Pasos:
  1. Verifica minikube y el addon ingress.
  2. Conecta Floci a la red de minikube y toma su IP (R3).
  3. Namespace, Secrets (desde .env) y EndpointSlice de Floci.
  4. Construye las imágenes DENTRO de minikube (`minikube docker-env`, lo recomendado por la
     doc de minikube para el runtime Docker): sin `image load`, que copiaba y descomprimía
     300 MB por imagen y tumbaba el nodo.
  5. Aplica los manifiestos y arranca los Deployments DE A UNO.

Reintentos (AWS Well-Architected REL05-BP03, Azure "transient faults"):
  - SOLO errores transitorios (API caída, webhook no listo, timeouts). Un error permanente
    (YAML inválido, imagen que no compila) falla de inmediato: reintentarlo no lo arregla.
  - Backoff exponencial con jitter completo y tope de intentos.
  - Cada reintento se registra y al final se imprime el resumen: si aparecen muchos, el
    problema es de capacidad del equipo, no algo que se arregle reintentando.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from retry import RETRY_LOG, execute, run, summary  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SERVICES = (  # orden de arranque: primero lo que el gateway llama, al final la UI
    "station-reservation-service",
    "billing-wallet-service",
    "energy-dispatch-service",
    "graphql-gateway",
    "frontend",
)


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def _api_running(_code: int, out: str) -> bool:
    line = next((ln for ln in out.splitlines() if ln.startswith("{")), "{}")
    return json.loads(line).get("APIServer") == "Running"


def check_cluster(profile: str) -> None:
    # `minikube status` sale con código != 0 si algo no corre: se juzga por el JSON. Si dice
    # "Stopped" no es transitorio (hay que arrancarlo), pero la API reiniciando sí lo es.
    code, out, err = execute(("minikube", "-p", profile, "status", "-o", "json"), None, None)
    if not _api_running(code, out):
        if '"Host":"Stopped"' in out.replace(" ", ""):
            sys.exit(f"minikube '{profile}' está detenido: minikube start -p {profile}")
        run("minikube", "-p", profile, "status", "-o", "json", ok=_api_running)
    addons = json.loads(run("minikube", "-p", profile, "addons", "list", "-o", "json"))
    if addons.get("ingress", {}).get("Status") != "enabled":
        sys.exit(f"Falta el addon: minikube -p {profile} addons enable ingress")


def connect_floci(profile: str, container: str) -> str:
    """Floci vive en la red de Compose; minikube en la suya. Se unen y se devuelve la IP."""
    networks = run("docker", "inspect", "-f", "{{json .NetworkSettings.Networks}}", container)
    if profile not in json.loads(networks):
        run("docker", "network", "connect", profile, container)
    ip = run(
        "docker",
        "inspect",
        "-f",
        f'{{{{(index .NetworkSettings.Networks "{profile}").IPAddress}}}}',
        container,
    )
    if not ip:
        sys.exit("No se pudo obtener la IP de Floci en la red de minikube")
    return ip


def minikube_docker_env(profile: str) -> dict[str, str]:
    """Variables para que `docker` hable con el daemon DENTRO del nodo de minikube."""
    env = dict(os.environ)
    out = run("minikube", "-p", profile, "docker-env", "--shell", "none")
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if value:
                env[key] = value
            else:
                env.pop(key, None)
    return env


def build_images(profile: str, services: list[str], tag: str) -> None:
    env = minikube_docker_env(profile)
    for svc in services:
        if svc == "frontend":
            cmd = ["docker", "build", "-q", "-t", f"aegisvolt/frontend:{tag}", "frontend"]
        else:
            cmd = [
                "docker", "build", "-q", "-f", f"services/{svc}/Dockerfile",
                "--build-arg", f"SERVICE_VERSION={tag}", "-t", f"aegisvolt/{svc}:{tag}", ".",
            ]  # fmt: skip
        started = time.time()
        run(*cmd, env=env, attempts=3)  # un Dockerfile roto es permanente: falla al instante
        print(f"    {svc}:{tag} en {time.time() - started:.0f} s")


def secret_yaml(kubectl: list[str], ns: str, name: str, data: dict[str, str]) -> str:
    literals = [f"--from-literal={k}={v}" for k, v in data.items()]
    return run(*kubectl, "-n", ns, "create", "secret", "generic", name, *literals,
               "--dry-run=client", "-o", "yaml")  # fmt: skip


def endpoint_slice(ns: str, ip: str) -> str:
    return json.dumps(
        {
            "apiVersion": "discovery.k8s.io/v1",
            "kind": "EndpointSlice",
            "metadata": {
                "name": "floci-external",
                "namespace": ns,
                "labels": {"kubernetes.io/service-name": "floci"},  # lo une al Service floci
            },
            "addressType": "IPv4",
            "ports": [{"name": "http", "port": 4566, "protocol": "TCP"}],
            "endpoints": [{"addresses": [ip], "conditions": {"ready": True}}],
        }
    )


def current_tag(kubectl: list[str], ns: str, deployment: str) -> str | None:
    code, image, _ = execute(
        (*kubectl, "-n", ns, "get", f"deployment/{deployment}", "-o",
         "jsonpath={.spec.template.spec.containers[0].image}"), None, None,
    )  # fmt: skip
    return image.rsplit(":", 1)[1] if code == 0 and ":" in image else None


def render(kubectl: list[str], overlay: Path, tags: dict[str, str]) -> list[str]:
    """Renderiza el overlay con los tags pedidos (transformer `images`) y lo parte en docs.

    kustomize exige rutas RELATIVAS (load restrictor; FAQ de kustomize: el overlay se usa como
    base desde otra kustomization). Por eso la carpeta temporal vive dentro de k8s/.
    """
    images = "\n".join(
        f'  - name: aegisvolt/{svc}\n    newTag: "{tag}"' for svc, tag in tags.items()
    )
    with tempfile.TemporaryDirectory(dir=ROOT / "k8s", prefix=".render-") as tmp:
        rel = Path(os.path.relpath(overlay, tmp)).as_posix()
        (Path(tmp) / "kustomization.yaml").write_text(
            f"resources:\n  - {rel}\nimages:\n{images}\n", encoding="utf-8"
        )
        out = run(*kubectl, "kustomize", tmp, attempts=1)
    return [doc for doc in re.split(r"^---$", out, flags=re.M) if doc.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", choices=("dev", "test", "prod"), default="dev")
    parser.add_argument("--profile", default="aegisvolt", help="perfil de minikube")
    parser.add_argument("--floci-container", default="floci")
    parser.add_argument(
        "--tag",
        help="tag a desplegar (CI: sha corto). Sin --tag cada servicio CONSERVA el que tiene "
        "(nunca se vuelve a una versión vieja por accidente). Obligatorio para construir.",
    )
    parser.add_argument("--skip-build", "--skip-images", action="store_true")
    parser.add_argument("--only", nargs="+", choices=SERVICES, help="los demás quedan en 0")
    args = parser.parse_args()

    if not args.skip_build and not args.tag:
        sys.exit("Para construir hace falta --tag (un tag NUEVO: el nodo cachea por tag)")
    started = time.time()
    ns = f"aegisvolt-{args.env}"
    kubectl = ["kubectl", "--context", args.profile, "--request-timeout=30s"]
    overlay = ROOT / "k8s" / "overlays" / args.env
    wanted = [s for s in SERVICES if not args.only or s in args.only]

    print(f"[1/5] Clúster minikube '{args.profile}'")
    check_cluster(args.profile)

    print("[2/5] Red Floci <-> minikube")
    floci_ip = connect_floci(args.profile, args.floci_container)
    print(f"  Floci en {floci_ip}:4566")

    print(f"[3/5] Namespace {ns}, Secrets y EndpointSlice")
    run(*kubectl, "apply", "-f", str(overlay / "namespace.yaml"))
    env = read_env_file()
    aws = {
        "AWS_ACCESS_KEY_ID": env.get("AWS_ACCESS_KEY_ID", "test"),  # FALSAS: solo Floci
        "AWS_SECRET_ACCESS_KEY": env.get("AWS_SECRET_ACCESS_KEY", "test"),
    }
    token = env.get("ADMIN_TOKEN")
    if not token:
        sys.exit("Falta ADMIN_TOKEN en .env")
    for name, data in (("aws-credentials", aws), ("gateway-admin", {"ADMIN_TOKEN": token})):
        run(*kubectl, "apply", "-f", "-", stdin=secret_yaml(kubectl, ns, name, data))
    run(*kubectl, "apply", "-f", "-", stdin=endpoint_slice(ns, floci_ip))

    print(f"[4/5] Imágenes {args.tag} (build dentro de minikube)")
    if not args.skip_build:
        build_images(args.profile, wanted, args.tag)

    print("[5/5] Manifiestos y arranque escalonado")
    # Sin --tag: cada servicio conserva lo desplegado (bug de la prueba: el default "v1"
    # regresó los servicios a v1 y el frontend quedó sin imagen).
    tags = {svc: args.tag or current_tag(kubectl, ns, svc) or "v1" for svc in SERVICES}
    # El gateway estable CONSERVA su versión siempre: solo canary.py la cambia tras medirla.
    tags["graphql-gateway"] = current_tag(kubectl, ns, "graphql-gateway") or tags["graphql-gateway"]
    print("  tags: " + ", ".join(f"{s}={t}" for s, t in tags.items()))
    print(f"  gateway estable: {tags['graphql-gateway']} (la versión nueva entra por canary)")
    docs = render(kubectl, overlay, tags)
    is_deploy = [re.search(r"^kind: Deployment$", d, flags=re.M) is not None for d in docs]
    others = "\n---\n".join(d for d, dep in zip(docs, is_deploy, strict=True) if not dep)
    run(*kubectl, "apply", "-f", "-", stdin=others, attempts=5)  # webhook del Ingress lento
    for doc in (d for d, dep in zip(docs, is_deploy, strict=True) if dep):
        name = re.search(r"^  name: (\S+)$", doc, flags=re.M).group(1)
        active = name in wanted  # el canary nunca está en `wanted`: canary.py lo sube
        if not active:
            doc = re.sub(r"^  replicas: \d+$", "  replicas: 0", doc, count=1, flags=re.M)
        run(*kubectl, "apply", "-f", "-", stdin=doc)
        if active:
            run(*kubectl, "-n", ns, "rollout", "status", f"deployment/{name}", "--timeout=300s")

    print(f"\nListo en {time.time() - started:.0f} s: http://{args.env}.aegisvolt.local")
    print(f"  activos: {', '.join(wanted)}")
    print(summary())


if __name__ == "__main__":
    main()
