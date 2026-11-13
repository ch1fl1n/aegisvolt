"""Utilidad de desarrollo local de AegisVolt (multiplataforma, solo librería estándar).

Uso:
    uv run python scripts/dev.py up       # levanta Floci y espera a que esté sano
    uv run python scripts/dev.py status   # muestra el estado
    uv run python scripts/dev.py down     # detiene Floci (conserva los datos)
    uv run python scripts/dev.py reset    # borra TODO el estado local (pide confirmación)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEALTH_URL = "http://localhost:4566/_floci/health"
TIMEOUT_S = 60


def run(cmd: list[str], quiet: bool = False) -> int:
    """Ejecuta un comando SIN shell (lista de argumentos => sin inyección)."""
    if not quiet:
        print(f"$ {' '.join(cmd)}")
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=ROOT,
        check=False,
        capture_output=quiet,
    )
    return result.returncode


def require(tool: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"ERROR: falta '{tool}' en el PATH.")


def health() -> dict | None:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:  # noqa: S310 (URL fija y local)
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
        return None


def wait_healthy() -> dict:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        data = health()
        if data is not None:
            return data
        time.sleep(1)
    sys.exit(f"ERROR: Floci no respondió en {TIMEOUT_S}s. Revisa: docker compose logs floci")


def cmd_up() -> None:
    require("docker")
    if run(["docker", "info"], quiet=True) != 0:
        sys.exit("ERROR: Docker no responde. Abre Docker Desktop y vuelve a intentar.")
    if run(["docker", "compose", "up", "-d"]) != 0:
        sys.exit("ERROR: falló docker compose up.")
    data = wait_healthy()
    running = sum(1 for s in data.get("services", {}).values() if s == "running")
    print(f"OK Floci {data.get('version')} sano · {running} servicios AWS emulados")


def cmd_status() -> None:
    data = health()
    print("Floci: APAGADO" if data is None else f"Floci: ENCENDIDO (v{data.get('version')})")
    run(["docker", "compose", "ps"])


def cmd_down() -> None:
    run(["docker", "compose", "down"])
    print("Floci detenido. Los datos siguen en el volumen 'floci-data'.")


def cmd_reset() -> None:
    prompt = "Esto BORRA todo el estado local de Floci (buckets, tablas, tfstate). Escribe BORRAR: "
    answer = input(prompt)
    if answer.strip() != "BORRAR":
        sys.exit("Cancelado.")
    run(["docker", "compose", "down", "-v"])
    print("Estado local eliminado.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Entorno local de AegisVolt")
    parser.add_argument("command", choices=["up", "status", "down", "reset"])
    args = parser.parse_args()
    {"up": cmd_up, "status": cmd_status, "down": cmd_down, "reset": cmd_reset}[args.command]()


if __name__ == "__main__":
    main()
