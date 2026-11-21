"""Canary del gateway GraphQL con promoción o rollback AUTOMÁTICO.

Uso:
    uv run python scripts/canary.py --env dev --tag v2                  # sano -> promueve
    uv run python scripts/canary.py --env dev --tag v2 --chaos 0.5      # roto -> rollback

Flujo:
  1. Despliega la versión nueva en graphql-gateway-canary (1 réplica) y espera a que esté lista.
  2. Le manda --weight % del tráfico (anotación canary-weight del Ingress canary).
  3. Genera tráfico por el Ingress y cuenta qué versión respondió (header x-service-version).
  4. Evalúa la versión canary con los datos del SERVIDOR en CloudWatch:
       plan A: métricas ErrorCount/RequestCount (dimensión Version) de los metric filters;
       plan B: si Floci no devuelve datapoints (R5), FilterLogEvents sobre los logs
               http_request de esa versión (el log stream empieza por la versión).
  5. Como Argo Rollouts (análisis Successful / Failed / Inconclusive):
       exit 0 = sano -> PROMUEVE
       exit 1 = FALLÓ (error > --max-error-rate) -> rollback
       exit 2 = INCONCLUSO (pocas peticiones o no se pudo medir) -> rollback igual
                (en CI no hay humano que decida: ante la duda, se vuelve a lo estable)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

import boto3
import httpx
from retry import execute, run, summary

QUERY = {"query": "{ flags { name enabled } }"}


class Kube:
    def __init__(self, context: str, namespace: str) -> None:
        self.base = ["kubectl", "--context", context, "-n", namespace]

    def __call__(self, *args: str, check: bool = True) -> str:
        # Misma política que deploy.py (retry.py): solo transitorios, backoff + jitter.
        # check=False (rollback): nunca aborta, intenta y sigue.
        if not check:
            print("  $ kubectl", " ".join(args))
            return execute((*self.base, *args), None, None)[1]
        return run(*self.base, *args)

    def set_weight(self, weight: int) -> None:
        self(
            "annotate",
            "ingress/graphql-gateway-canary",
            f"nginx.ingress.kubernetes.io/canary-weight={weight}",
            "--overwrite",
        )


def deploy_canary(kube: Kube, tag: str, chaos: float) -> None:
    image = f"aegisvolt/graphql-gateway:{tag}"
    kube("set", "image", "deployment/graphql-gateway-canary", f"app={image}")
    kube(
        "set",
        "env",
        "deployment/graphql-gateway-canary",
        f"CHAOS_ERROR_RATE={chaos}",
    )
    kube("scale", "deployment/graphql-gateway-canary", "--replicas=1")
    kube("rollout", "status", "deployment/graphql-gateway-canary", "--timeout=180s")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def generate_traffic(context: str, host: str, requests: int) -> Counter[tuple[str, int]]:
    """Port-forward al Ingress controller y peticiones con el Host del ambiente."""
    port = free_port()
    pf = subprocess.Popen(  # noqa: S603
        ["kubectl", "--context", context, "-n", "ingress-nginx", "port-forward",  # noqa: S607
         "svc/ingress-nginx-controller", f"{port}:80"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    seen: Counter[tuple[str, int]] = Counter()
    try:
        url = f"http://127.0.0.1:{port}/graphql"
        with httpx.Client(timeout=5, headers={"Host": host}) as client:
            # Calentamiento: hasta 60 s a que el port-forward abra y el Ingress responda 200
            # (sin esto, un 503 del Ingress por pods aún no listos se contaría como tráfico).
            for _ in range(120):
                try:
                    if client.get(f"http://127.0.0.1:{port}/readyz").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            for _ in range(requests):
                try:
                    resp = client.post(url, json=QUERY)
                    seen[(resp.headers.get("x-service-version", "?"), resp.status_code)] += 1
                except httpx.TransportError:
                    seen[("?", 0)] += 1
                time.sleep(0.05)
    finally:
        pf.terminate()
    return seen


def metric_sum(cw, namespace: str, name: str, version: str, since: datetime) -> float | None:
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=name,
        Dimensions=[
            {"Name": "Service", "Value": "graphql-gateway"},
            {"Name": "Version", "Value": version},
        ],
        StartTime=since,
        EndTime=datetime.now(UTC),
        Period=60,
        Statistics=["Sum"],
    )
    points = resp.get("Datapoints", [])
    return sum(p["Sum"] for p in points) if points else None


def from_logs(logs, group: str, version: str, since: datetime) -> tuple[int, int]:
    """Plan B (R5): cuenta peticiones y 5xx en los logs http_request de esa versión."""
    total = errors = 0
    kwargs = {
        "logGroupName": group,
        "logStreamNamePrefix": f"{version}/",
        "startTime": int(since.timestamp() * 1000),
        "filterPattern": '{ $.event = "http_request" }',
    }
    while True:
        page = logs.filter_log_events(**kwargs)
        for event in page.get("events", []):
            record = json.loads(event["message"])
            if record.get("version") != version:
                continue
            total += 1
            errors += int(record.get("status", 0)) >= 500
        token = page.get("nextToken")
        if not token or not page.get("events"):
            return total, errors
        kwargs["nextToken"] = token


def evaluate(env: str, version: str, since: datetime) -> tuple[int, int, str]:
    session = boto3.session.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    cw = session.client("cloudwatch", endpoint_url=endpoint)
    requests = metric_sum(cw, f"AegisVolt/{env}", "RequestCount", version, since)
    if requests:
        errors = metric_sum(cw, f"AegisVolt/{env}", "ErrorCount", version, since) or 0
        return int(requests), int(errors), "métricas (plan A)"
    logs = session.client("logs", endpoint_url=endpoint)
    total, errors = from_logs(logs, f"/aegisvolt/{env}/graphql-gateway", version, since)
    return total, errors, "FilterLogEvents (plan B: Floci no da datapoints)"


def promote(kube: Kube, tag: str) -> None:
    kube.set_weight(100)  # todo el tráfico al canary mientras se actualiza el estable
    kube("set", "image", "deployment/graphql-gateway", f"app=aegisvolt/graphql-gateway:{tag}")
    kube("rollout", "status", "deployment/graphql-gateway", "--timeout=180s")
    kube.set_weight(0)
    kube("scale", "deployment/graphql-gateway-canary", "--replicas=0")


def rollback(kube: Kube) -> None:
    # check=False: el rollback intenta TODO aunque un paso falle (nunca se queda a medias).
    kube(
        "annotate", "ingress/graphql-gateway-canary",
        "nginx.ingress.kubernetes.io/canary-weight=0", "--overwrite", check=False,
    )  # fmt: skip  # primero se corta el tráfico, después se apaga
    kube("scale", "deployment/graphql-gateway-canary", "--replicas=0", check=False)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--env", choices=("dev", "test", "prod"), default="dev")
    p.add_argument("--context", default="aegisvolt")
    p.add_argument("--tag", required=True, help="versión nueva, p. ej. v2")
    p.add_argument("--weight", type=int, default=20, help="%% de tráfico al canary")
    p.add_argument("--traffic", type=int, default=200, help="peticiones de prueba")
    p.add_argument("--window", type=int, default=15, help="segundos de espera para los logs")
    p.add_argument("--min-requests", type=int, default=20)
    p.add_argument("--max-error-rate", type=float, default=0.05)
    p.add_argument("--chaos", type=float, default=0.0, help="fracción de 500 inducidos")
    args = p.parse_args()

    kube = Kube(args.context, f"aegisvolt-{args.env}")
    # La métrica se filtra por Version: si estable y canary tienen el MISMO tag, los errores
    # del canary se diluyen con el tráfico sano del estable (prueba ronda 2: 12/150 = 8 %, cuando
    # el canary tenía ~50 %). Con más dilución una versión rota podría PROMOVERSE. Se aborta.
    try:  # antes de tocar nada: si no se puede leer el estable, es inconcluso (exit 2)
        # API sana antes de medir (anti-choques). En Python y no en el shell: Git Bash
        # convertía "/readyz" en una ruta de Windows y la espera nunca pasaba (bitácora).
        kube("get", "--raw", "/readyz")
        stable_image = kube(
            "get", "deployment/graphql-gateway", "-o",
            "jsonpath={.spec.template.spec.containers[0].image}",
        )  # fmt: skip
    except SystemExit as exc:
        print(f"ABORTADO (inconcluso): no se pudo leer el estable ({exc}); nada se modificó")
        return 2
    if stable_image.endswith(f":{args.tag}"):
        print(
            f"ABORTADO (inconcluso): el estable ya es {args.tag}; usa un tag NUEVO para el canary"
        )
        return 2
    since = datetime.now(UTC) - timedelta(seconds=5)

    # Fail-safe: si CUALQUIER paso falla (canary que no arranca, API caída, CloudWatch sin
    # responder) se revierte. Bug de la prueba: un timeout dejaba el canary encendido.
    try:
        print(f"[1/4] Canary {args.tag} (chaos={args.chaos})")
        deploy_canary(kube, args.tag, args.chaos)

        print(f"[2/4] {args.weight}% del tráfico al canary")
        kube.set_weight(args.weight)
        time.sleep(3)  # ingress-nginx recarga la configuración

        print(f"[3/4] {args.traffic} peticiones por el Ingress")
        seen = generate_traffic(args.context, f"{args.env}.aegisvolt.local", args.traffic)
        for (version, status), count in sorted(seen.items()):
            print(f"  cliente: versión={version} status={status} -> {count}")
        time.sleep(args.window)  # los logs llegan a CloudWatch en lotes cada ~2 s

        print("[4/4] Evaluación con datos del servidor")
        total, errors, source = evaluate(args.env, args.tag, since)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"ROLLBACK (inconcluso): el canary no se pudo evaluar ({exc})")
        rollback(kube)
        return 2
    rate = errors / total if total else 1.0
    print(f"  fuente: {source}")
    print(f"  {args.tag}: {total} peticiones, {errors} con 5xx -> {rate:.1%}")

    if total < args.min_requests:
        print(f"ROLLBACK (inconcluso): solo {total} peticiones (< {args.min_requests})")
        rollback(kube)
        return 2
    if rate > args.max_error_rate:
        print(f"ROLLBACK: tasa de error {rate:.1%} > {args.max_error_rate:.0%}")
        rollback(kube)
        return 1
    print(f"PROMOCIÓN: {rate:.1%} <= {args.max_error_rate:.0%}; {args.tag} pasa a estable")
    promote(kube, args.tag)
    print(summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
