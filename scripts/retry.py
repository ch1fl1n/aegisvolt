"""Política de reintentos compartida por deploy.py y canary.py.

Basada en AWS Well-Architected REL05-BP03 y Azure "Transient fault handling":
  - reintentar SOLO errores transitorios (se arreglan esperando);
  - backoff exponencial con jitter completo y tope de intentos;
  - un error permanente falla al instante (reintentarlo no lo arregla);
  - cada reintento queda registrado para medir si ayuda o esconde un problema de capacidad.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import time
from collections.abc import Callable

TRANSIENT = re.compile(
    r"TLS handshake timeout|connection refused|connection reset|\bEOF\b|i/o timeout"
    r"|context deadline exceeded|Unable to connect to the server|failed calling webhook"
    r"|ServiceUnavailable|the server is currently unable|took an unusually long time"
    r"|error during connect|Cannot connect to the Docker daemon"
    r"|frontend grpc server closed unexpectedly",  # BuildKit se cae bajo carga; reintentar sí ayuda
    re.IGNORECASE,
)
RETRY_LOG: list[str] = []


def _show(cmd: tuple[str, ...]) -> str:
    return " ".join(re.sub(r"^(--from-literal=[^=]+=).*", r"\1***", c) for c in cmd)  # sin secretos


def execute(cmd: tuple[str, ...], stdin: str | None, env: dict | None) -> tuple[int, str, str]:
    proc = subprocess.run(  # noqa: S603
        cmd, input=stdin, capture_output=True, text=True, check=False, env=env,
        encoding="utf-8", errors="replace",  # la salida de docker/kubectl puede traer bytes raros
    )  # fmt: skip
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def run(
    *cmd: str,
    stdin: str | None = None,
    env: dict | None = None,
    attempts: int = 4,
    ok: Callable[[int, str], bool] = lambda code, _out: code == 0,
    quiet: bool = False,
) -> str:
    """Ejecuta `cmd`; reintenta SOLO si el error es transitorio, con backoff + jitter."""
    if not quiet:
        print("  $", _show(cmd))
    for attempt in range(1, attempts + 1):
        code, out, err = execute(cmd, stdin, env)
        if ok(code, out):
            return out
        last = next((ln for ln in reversed((err or out).splitlines()) if ln.strip()), "sin salida")
        what = " ".join(cmd[:2])
        if not TRANSIENT.search(f"{err}\n{out}"):
            sys.exit(f"ERROR permanente en `{what}`: {last}")
        if attempt == attempts:
            sys.exit(f"ERROR: {attempts} intentos agotados en `{_show(cmd)[:80]}`: {last}")
        wait = random.uniform(1, min(30.0, 2.0 * 2**attempt))  # noqa: S311 (jitter, no cripto)
        RETRY_LOG.append(f"{what}: {last[:90]}")
        print(f"    intento {attempt}/{attempts} falló (transitorio): {last[:90]}")
        print(f"    reintento en {wait:.1f} s")
        time.sleep(wait)
    raise AssertionError("inalcanzable")


def summary() -> str:
    lines = [f"  reintentos transitorios: {len(RETRY_LOG)}"]
    lines += [f"    - {item}" for item in RETRY_LOG]
    return "\n".join(lines)
