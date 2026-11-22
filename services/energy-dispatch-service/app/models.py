"""Modelos del dominio y contratos de entrada/salida (validados por Pydantic)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

ID_PATTERN = r"^[A-Za-z0-9-]{1,64}$"
SafeId = Annotated[str, Field(pattern=ID_PATTERN)]


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    FAULTED = "FAULTED"  # el cargador falló al iniciar


class Session(BaseModel):
    saga_id: str
    station_id: str
    connector_id: str
    vehicle_id: str
    power_kw: float
    status: SessionStatus
    started_at: str
    ended_at: str | None = None


class StartRequest(BaseModel):
    saga_id: SafeId
    station_id: SafeId
    connector_id: SafeId
    vehicle_id: SafeId
    power_kw: float = Field(gt=0, le=400)  # el orquestador lo sube si hay FAST_CHARGE_BOOST
    fault_injection: bool = False  # SIMULATE_CHARGER_HARDWARE_FAULT (prohibido en prod)


class StopResult(BaseModel):
    saga_id: str
    stopped: bool  # False = ya estaba detenida o no existía (idempotente)
