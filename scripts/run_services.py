"""Levanta los 4 servicios de AegisVolt en local (sin Docker) contra Floci.

Uso (Floci arriba: `uv run python scripts/dev.py up`):
    uv run python scripts/run_services.py

Ctrl+C detiene los 4. Lee .env (AWS_*, AEGIS_ENV, ADMIN_TOKEN). En la Fase 4 esto lo
reemplaza compose.apps.yaml y en la Fase 5 Kubernetes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = [  # (nombre = SERVICE_NAME = carpeta, puerto)
    ("station-reservation-service", 8001),
    ("billing-wallet-service", 8002),
    ("energy-dispatch-service", 8003),
    ("graphql-gateway", 8000),
]
READY_TIMEOUT_S = 40


def load_dotenv() -> dict[str, str]:
    """Variables de .env; las que ya están en el entorno tienen prioridad."""
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return {**values, **os.environ}


def ready(port: int) -> bool:
    try:
        url = f"http://127.0.0.1:{port}/readyz"
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 (URL local fija)
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def main() -> None:
    base_env = load_dotenv()
    if not base_env.get("ADMIN_TOKEN"):
        sys.exit("ERROR: falta ADMIN_TOKEN en .env (ver .env.example).")

    procs: list[subprocess.Popen[bytes]] = []
    try:
        for name, port in SERVICES:
            env = {**base_env, "SERVICE_NAME": name}
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:build",
                "--factory",
                "--app-dir",
                str(ROOT / "services" / name),
                "--port",
                str(port),
                "--no-access-log",  # el middleware ya escribe un log JSON por petición
            ]
            procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env))  # noqa: S603 (sin shell)

        deadline = time.monotonic() + READY_TIMEOUT_S
        pending = {name: port for name, port in SERVICES}
        while pending and time.monotonic() < deadline:
            pending = {n: p for n, p in pending.items() if not ready(p)}
            time.sleep(0.5)
        if pending:
            sys.exit(f"ERROR: no quedaron listos: {', '.join(pending)}. Revisa los logs.")

        print("\nOK los 4 servicios están listos:")
        for name, port in SERVICES:
            print(f"  {name:<30} http://localhost:{port}")
        print("  GraphiQL (explorador)          http://localhost:8000/graphql")
        print("Ctrl+C para detenerlos.\n", flush=True)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        sys.exit("ERROR: un servicio se detuvo inesperadamente. Revisa los logs.")
    except KeyboardInterrupt:
        print("\nDeteniendo servicios...")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
