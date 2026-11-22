"""Reglas de la auditoría de sagas, SIN Prefect ni AWS (se prueban con datos de ejemplo).

Una saga es una transacción distribuida: cada servicio guarda su parte en SU tabla.
La auditoría cruza la bitácora (tabla sagas) con lo que quedó en reservas y cobros:

  huérfana       -> sigue en un estado intermedio mucho después de su última actualización
                    (el gateway murió a mitad de camino y nadie compensó).
  inconsistente  -> el estado final no coincide con los efectos en los servicios:
                    COMPLETED sin reserva o sin cobro; COMPENSATED con la reserva aún tomada
                    o con un cobro sin su reembolso.
  fallida        -> FAILED: una compensación falló; requiere revisión humana.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

TERMINAL = {"COMPLETED", "COMPENSATED", "FAILED"}


@dataclass(frozen=True)
class Effects:
    """Lo que los servicios de dominio tienen guardado para UNA saga."""

    reservation_held: bool  # hay un conector RESERVED con este saga_id
    charged: bool  # hay transacción CHARGE
    refunded: bool  # hay transacción REFUND


@dataclass
class AuditReport:
    total: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    orphans: list[str] = field(default_factory=list)
    inconsistent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not (self.orphans or self.inconsistent or self.failed)


def is_orphan(saga: dict, now: datetime, max_age: timedelta) -> bool:
    if saga["status"] in TERMINAL:
        return False
    updated = datetime.fromisoformat(saga["updated_at"])
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return now - updated > max_age


def inconsistency(saga: dict, fx: Effects) -> str | None:
    """Devuelve el motivo si los efectos no cuadran con el estado final, o None."""
    status = saga["status"]
    if status == "COMPLETED":
        if not fx.reservation_held:
            return "COMPLETED sin reserva del conector"
        if not fx.charged or fx.refunded:
            return "COMPLETED sin cobro vigente"
    if status == "COMPENSATED":
        if fx.reservation_held:
            return "COMPENSATED pero el conector sigue reservado"
        if fx.charged and not fx.refunded:
            return "COMPENSATED con cobro sin reembolso"
    return None


def build_report(
    sagas: list[dict], effects: dict[str, Effects], now: datetime, max_age: timedelta
) -> AuditReport:
    report = AuditReport(total=len(sagas))
    for saga in sagas:
        sid, status = saga["saga_id"], saga["status"]
        report.by_status[status] = report.by_status.get(status, 0) + 1
        if status == "FAILED":
            report.failed.append(sid)
        if is_orphan(saga, now, max_age):
            report.orphans.append(sid)
        if sid in effects and (why := inconsistency(saga, effects[sid])):
            report.inconsistent.append(f"{sid}: {why}")
    return report
