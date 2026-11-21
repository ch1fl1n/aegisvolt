"""Flujo de Prefect: salud de un ambiente.

    .venv/Scripts/python health_flow.py --env dev

Revisa tres cosas y falla si alguna está mal:
  1. Floci (la "nube") responde.
  2. Cada tabla DynamoDB del ambiente existe y está ACTIVE.
  3. Tasa de 5xx por servicio en los últimos N minutos, leída de CloudWatch Logs
     (los mismos logs http_request que usa el canary; FilterLogEvents porque Floci no
     devuelve datapoints de los metric filters, R5).
"""

from __future__ import annotations

import argparse
import json
import os
import time

import boto3
import httpx
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_table_artifact

SERVICES = (
    "station-reservation-service",
    "billing-wallet-service",
    "energy-dispatch-service",
    "graphql-gateway",
)
TABLES = ("reservations", "billing", "dispatch", "sagas", "flags")
ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")


def _client(name: str):
    return boto3.client(
        name,
        endpoint_url=ENDPOINT,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),  # FALSAS: Floci
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


@task(retries=3, retry_delay_seconds=5)
def check_floci() -> bool:
    return httpx.get(f"{ENDPOINT}/_floci/health", timeout=5).status_code == 200


@task
def check_tables(env: str) -> dict[str, str]:
    ddb = _client("dynamodb")
    status = {}
    for name in TABLES:
        table = f"aegisvolt-{name}-{env}"
        try:
            status[table] = ddb.describe_table(TableName=table)["Table"]["TableStatus"]
        except ddb.exceptions.ResourceNotFoundException:
            status[table] = "MISSING"
    return status


@task
def error_rate(env: str, service: str, minutes: int) -> dict:
    logs = _client("logs")
    kwargs = {
        "logGroupName": f"/aegisvolt/{env}/{service}",
        "startTime": int((time.time() - minutes * 60) * 1000),
        "filterPattern": '{ $.event = "http_request" }',
    }
    total = errors = 0
    try:
        while True:
            page = logs.filter_log_events(**kwargs)
            for event in page.get("events", []):
                total += 1
                errors += int(json.loads(event["message"]).get("status", 0)) >= 500
            if not page.get("nextToken") or not page.get("events"):
                break
            kwargs["nextToken"] = page["nextToken"]
    except logs.exceptions.ResourceNotFoundException:
        pass  # sin log group = el servicio nunca escribió en este ambiente
    return {"service": service, "requests": total, "errors": errors,
            "rate": round(errors / total, 4) if total else 0.0}  # fmt: skip


@flow(name="environment-health", log_prints=True)
def environment_health(env: str = "dev", minutes: int = 15, max_error_rate: float = 0.05):
    logger = get_run_logger()
    problems = []
    if not check_floci():
        problems.append("Floci no responde")
    for table, status in check_tables(env).items():
        if status != "ACTIVE":
            problems.append(f"tabla {table}: {status}")
    rates = [error_rate(env, svc, minutes) for svc in SERVICES]
    problems += [
        f"{r['service']}: {r['rate']:.1%} de 5xx ({r['errors']}/{r['requests']})"
        for r in rates
        if r["rate"] > max_error_rate
    ]
    create_table_artifact(key=f"health-{env}", table=rates, description=f"Últimos {minutes} min")
    for r in rates:
        logger.info("%s: %s peticiones, %s errores", r["service"], r["requests"], r["errors"])
    if problems:
        raise RuntimeError(f"{env} NO saludable: " + "; ".join(problems))
    return rates


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev", choices=("dev", "test", "prod"))
    environment_health(env=parser.parse_args().env)
