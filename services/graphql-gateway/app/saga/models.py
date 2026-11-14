"""Estado de una saga: lo que se guarda en la bitácora (tabla sagas)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

ID_PATTERN = r"^[A-Za-z0-9-]{1,64}$"
SafeId = Annotated[str, Field(pattern=ID_PATTERN)]


class SagaStatus(StrEnum):
    STARTED = "STARTED"
    RESERVED = "RESERVED"
    CHARGED = "CHARGED"
    COMPLETED = "COMPLETED"  # camino feliz: la sesión de carga quedó activa
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"  # falló un paso y todo se deshizo bien
    FAILED = "FAILED"  # una compensación falló: requiere revisión


TERMINAL_STATUSES = frozenset({SagaStatus.COMPLETED, SagaStatus.COMPENSATED, SagaStatus.FAILED})


class StepName(StrEnum):
    RESERVE_CONNECTOR = "reserve_connector"
    CHARGE_WALLET = "charge_wallet"
    START_CHARGING = "start_charging"


class StepRecord(BaseModel):
    step: StepName
    action: Literal["do", "compensate"]
    outcome: Literal["ok", "error"]
    at: str
    detail: str | None = None


class StartChargeInput(BaseModel):
    """Lo que pide el cliente (frontend) para iniciar una carga."""

    # Opcional: si el cliente genera el id, puede suscribirse ANTES de lanzar la saga
    # y reintentar la mutación sin crear una saga nueva (llave de idempotencia).
    saga_id: SafeId | None = None
    station_id: SafeId
    connector_id: SafeId
    vehicle_id: SafeId
    account_id: SafeId
    energy_kwh: float = Field(ge=1, le=200)


class SagaRecord(BaseModel):
    saga_id: str
    status: SagaStatus
    station_id: str
    connector_id: str
    vehicle_id: str
    account_id: str
    energy_kwh: float
    amount_cents: int
    power_kw: float
    flags: dict[str, bool]  # foto de las flags al iniciar (auditoría)
    history: list[StepRecord] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str
