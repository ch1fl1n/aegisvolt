"""Reglas de auditoría de sagas (sin Prefect ni AWS)."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "observability" / "prefect"))

from audit_rules import Effects, build_report  # noqa: E402

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
OLD = (NOW - timedelta(minutes=30)).isoformat()
NEW = (NOW - timedelta(seconds=10)).isoformat()


def saga(sid: str, status: str, updated: str = NEW) -> dict:
    return {"saga_id": sid, "status": status, "updated_at": updated}


def test_detecta_huerfanas_inconsistentes_y_fallidas():
    sagas = [
        saga("ok", "COMPLETED"),
        saga("comp-ok", "COMPENSATED"),
        saga("en-curso", "CHARGED"),  # reciente: todavía no es huérfana
        saga("huerfana", "RESERVED", OLD),
        saga("sin-reembolso", "COMPENSATED"),
        saga("rota", "FAILED"),
    ]
    effects = {
        "ok": Effects(reservation_held=True, charged=True, refunded=False),
        "comp-ok": Effects(reservation_held=False, charged=True, refunded=True),
        "sin-reembolso": Effects(reservation_held=False, charged=True, refunded=False),
    }
    report = build_report(sagas, effects, NOW, timedelta(minutes=5))
    assert report.orphans == ["huerfana"]
    assert report.inconsistent == ["sin-reembolso: COMPENSATED con cobro sin reembolso"]
    assert report.failed == ["rota"]
    assert report.by_status["COMPENSATED"] == 2
    assert not report.healthy


def test_todo_cuadra():
    sagas = [saga("ok", "COMPLETED")]
    effects = {"ok": Effects(reservation_held=True, charged=True, refunded=False)}
    assert build_report(sagas, effects, NOW, timedelta(minutes=5)).healthy
