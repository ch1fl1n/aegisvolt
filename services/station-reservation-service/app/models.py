"""Modelos del dominio y contratos de entrada (validados por Pydantic)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

# IDs con formato seguro: evita claves raras en DynamoDB y log injection.
SafeId = Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{1,64}$")]


class ConnectorStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    FAULTED = "FAULTED"  # avería física: no se puede reservar


class Connector(BaseModel):
    station_id: str
    connector_id: str
    power_kw: float
    status: ConnectorStatus
    saga_id: str | None = None
    vehicle_id: str | None = None
    reserved_at: str | None = None


class ConnectorIn(BaseModel):
    """Alta o actualización de inventario de un conector."""

    power_kw: float = Field(gt=0, le=400)
    status: ConnectorStatus = ConnectorStatus.AVAILABLE


class ReservationRequest(BaseModel):
    saga_id: SafeId
    station_id: SafeId
    connector_id: SafeId
    vehicle_id: SafeId


class ReleaseRequest(BaseModel):
    """Compensación: se manda la clave exacta para no depender del GSI (eventual)."""

    saga_id: SafeId
    station_id: SafeId
    connector_id: SafeId
