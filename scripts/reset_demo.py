"""Deja dev como al empezar una demo: conectores libres, saldos iniciales y flags apagadas.

    uv run python scripts/reset_demo.py          (~30 s; correr antes de la demo y tras un ensayo)

Una carga COMPLETED deja su conector RESERVED (está cargando) y seed.py no pisa reservas
activas (409). Aquí se liberan por la API del servicio (POST /reservations/release, la misma
compensación de la SAGA, idempotente) y luego seed.py restaura saldos y apaga las flags.
Nunca escribe directo en las tablas de dominio; solo LEE la de reservas para saber qué liberar.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import boto3
import httpx

ROOT = Path(__file__).resolve().parent.parent
NS = "aegisvolt-dev"
DEMO_STATIONS = ("st-norte", "st-centro", "st-sur")
FORWARDS = {  # servicio -> puerto local (los que espera seed.py)
    "graphql-gateway": 8000,
    "station-reservation-service": 8001,
    "billing-wallet-service": 8002,
}


def wait_ready(url: str) -> None:
    for _ in range(90):
        try:
            if httpx.get(url, timeout=3).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(1)
    sys.exit(f"ERROR: {url} no respondió (¿dev está arriba?)")


def reserved_connectors() -> list[dict]:
    ddb = boto3.resource(
        "dynamodb",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
        region_name="us-east-1",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),  # FALSAS: Floci
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )
    table = ddb.Table("aegisvolt-reservations-dev")
    items = []
    for station in DEMO_STATIONS:
        resp = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("station_id").eq(station)
        )
        items += [i for i in resp["Items"] if i.get("status") == "RESERVED" and i.get("saga_id")]
    return items


def main() -> int:
    t0 = time.time()
    procs = [
        subprocess.Popen(  # noqa: S603
            ["kubectl", "-n", NS, "port-forward", f"svc/{svc}", f"{port}:8000"],  # noqa: S607
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for svc, port in FORWARDS.items()
    ]
    try:
        for port in FORWARDS.values():
            wait_ready(f"http://127.0.0.1:{port}/readyz")

        busy = reserved_connectors()
        print(f"[1/2] liberar conectores reservados de la demo: {len(busy)}")
        with httpx.Client(timeout=30) as http:
            for c in busy:
                body = {
                    "saga_id": c["saga_id"],
                    "station_id": c["station_id"],
                    "connector_id": c["connector_id"],
                }
                url = "http://127.0.0.1:8001/reservations/release"
                http.post(url, json=body).raise_for_status()
                print(f"  - {c['station_id']}/{c['connector_id']} -> AVAILABLE")

        print("[2/2] saldos iniciales y flags apagadas (seed.py --reset-flags)")
        seed = [sys.executable, str(ROOT / "scripts" / "seed.py"), "--reset-flags"]
        rc = subprocess.call(seed)  # noqa: S603
        if rc != 0:
            return rc
    finally:
        for p in procs:
            p.terminate()
    print(f"Listo en {time.time() - t0:.0f} s: dev limpio para la demo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
