"""Sigue una saga por su correlation_id en los logs de CloudWatch de los 4 servicios (§6.4).

    uv run python scripts/trace_saga.py                 # la última saga COMPENSADA de dev
    uv run python scripts/trace_saga.py --saga <id>     # una saga concreta
    uv run python scripts/trace_saga.py --env test

1. Busca en el log del gateway el evento `saga_finished` (filtro JSON de CloudWatch).
2. Toma su correlation_id (lo propaga el gateway en el header x-correlation-id).
3. Lo busca en los log groups /aegisvolt/<env>/<servicio> y muestra la línea de tiempo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import boto3

SERVICES = (
    "graphql-gateway",
    "station-reservation-service",
    "billing-wallet-service",
    "energy-dispatch-service",
)


def events(logs, group: str, pattern: str) -> list[dict]:
    out: list[dict] = []
    kwargs = {"logGroupName": group, "filterPattern": pattern}
    while True:
        page = logs.filter_log_events(**kwargs)
        out += page.get("events", [])
        token = page.get("nextToken")
        if not token or not page.get("events"):
            return out
        kwargs["nextToken"] = token


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--env", default="dev", choices=("dev", "test", "prod"))
    p.add_argument("--saga", help="saga_id (por defecto: la última compensada)")
    args = p.parse_args()
    logs = boto3.client(
        "logs",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),  # FALSAS: Floci
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )
    gw = f"/aegisvolt/{args.env}/graphql-gateway"
    if args.saga:
        pattern = f'{{ $.event = "saga_finished" && $.saga_id = "{args.saga}" }}'
    else:
        pattern = '{ $.event = "saga_finished" && $.outcome = "compensated" }'
    found = events(logs, gw, pattern)
    if not found:
        print("No hay sagas que cumplan el filtro en", gw)
        return 1
    last = json.loads(max(found, key=lambda e: e["timestamp"])["message"])
    cid = last["correlation_id"]
    print(f"saga {last['saga_id']} -> {last['outcome'].upper()} ({last.get('code')})")
    print(f"correlation_id {cid}\n")

    timeline = []
    for svc in SERVICES:
        evs = events(logs, f"/aegisvolt/{args.env}/{svc}", f'{{ $.correlation_id = "{cid}" }}')
        print(f"  {svc:<29} {len(evs):>3} eventos")
        timeline += [json.loads(e["message"]) for e in evs]
    print("\nLínea de tiempo (sin logs de httpx):")
    for r in sorted(timeline, key=lambda r: r["timestamp"]):
        if r.get("logger") == "httpx":
            continue
        print(f"  {r['timestamp'][11:23]}  {r['service']:<29} {r['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
