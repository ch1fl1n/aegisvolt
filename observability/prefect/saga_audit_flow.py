"""Flujo de Prefect: auditoría de sagas de un ambiente (huérfanas, compensadas, inconsistentes).

    .venv/Scripts/python saga_audit_flow.py --env dev

Solo LEE las tablas de DynamoDB (nunca corrige: eso lo decide una persona). Publica un
artifact markdown en la UI de Prefect y falla si encuentra algo para que se vea en rojo.
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta

import boto3
from audit_rules import TERMINAL, AuditReport, Effects, build_report
from boto3.dynamodb.conditions import Key
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact


def _ddb():
    return boto3.resource(
        "dynamodb",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),  # FALSAS: Floci
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


@task(retries=2, retry_delay_seconds=5)
def load_sagas(env: str) -> list[dict]:
    table = _ddb().Table(f"aegisvolt-sagas-{env}")
    items, kwargs = [], {}
    while True:  # Scan paginado: la auditoría recorre TODA la bitácora
        page = table.scan(**kwargs)
        items += page.get("Items", [])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


@task(retries=2, retry_delay_seconds=5)
def load_effects(env: str, saga_ids: list[str]) -> dict[str, Effects]:
    ddb = _ddb()
    reservations = ddb.Table(f"aegisvolt-reservations-{env}")
    billing = ddb.Table(f"aegisvolt-billing-{env}")
    effects = {}
    for sid in saga_ids:  # GSI by-saga en ambas tablas: una consulta por saga
        held = reservations.query(
            IndexName="by-saga", KeyConditionExpression=Key("saga_id").eq(sid)
        )
        txs = billing.query(IndexName="by-saga", KeyConditionExpression=Key("saga_id").eq(sid))
        types = {t.get("tx_type") or t["sk"].rsplit("#", 1)[-1] for t in txs.get("Items", [])}
        effects[sid] = Effects(
            reservation_held=any(i.get("status") == "RESERVED" for i in held.get("Items", [])),
            charged="CHARGE" in types,
            refunded="REFUND" in types,
        )
    return effects


def to_markdown(env: str, report: AuditReport) -> str:
    lines = [f"# Auditoría de sagas · `{env}`", "", f"Total: **{report.total}**", ""]
    lines += [f"- {status}: {count}" for status, count in sorted(report.by_status.items())]
    for title, items in (
        ("Huérfanas", report.orphans),
        ("Inconsistentes", report.inconsistent),
        ("Fallidas (compensación con error)", report.failed),
    ):
        lines += ["", f"## {title}: {len(items)}", *[f"- `{i}`" for i in items[:50]]]
    return "\n".join(lines)


@flow(name="saga-audit", log_prints=True)
def saga_audit(env: str = "dev", orphan_minutes: int = 5) -> dict:
    logger = get_run_logger()
    sagas = load_sagas(env)
    finished = [s["saga_id"] for s in sagas if s["status"] in TERMINAL - {"FAILED"}]
    effects = load_effects(env, finished)
    report = build_report(sagas, effects, datetime.now(UTC), timedelta(minutes=orphan_minutes))
    create_markdown_artifact(
        key=f"saga-audit-{env}", markdown=to_markdown(env, report), description="Auditoría"
    )
    logger.info(
        "sagas=%s por_estado=%s huérfanas=%s inconsistentes=%s fallidas=%s",
        report.total, report.by_status, len(report.orphans),
        len(report.inconsistent), len(report.failed),
    )  # fmt: skip
    if not report.healthy:
        raise RuntimeError(f"Auditoría de {env} con hallazgos (ver artifact saga-audit-{env})")
    return {"total": report.total, "by_status": report.by_status}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev", choices=("dev", "test", "prod"))
    saga_audit(env=parser.parse_args().env)
