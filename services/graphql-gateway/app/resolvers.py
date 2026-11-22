"""Lógica detrás de cada campo GraphQL (sin tipos de Strawberry: esos van en schema.py)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .clients import Clients, DownstreamError
from .config import GatewaySettings
from .flags import Flag, FlagStore
from .saga.models import ID_PATTERN, TERMINAL_STATUSES, SagaRecord, SagaStatus, StartChargeInput
from .saga.orchestrator import SagaOrchestrator
from .security import PublicError, require_admin

MAX_LIST = 50
WATCH_MAX_S = 300.0  # una suscripción a una saga no queda abierta para siempre


@dataclass
class Deps:
    """Todo lo que necesitan los resolvers. main.py lo arma; las pruebas lo falsean."""

    settings: GatewaySettings
    clients: Clients
    flags: FlagStore
    orchestrator: SagaOrchestrator
    poll_interval_s: float = 1.0  # suscripciones: cada cuánto se consulta DynamoDB


def _safe_id(value: str, field: str) -> str:
    if not re.fullmatch(ID_PATTERN, value):
        raise PublicError("VALIDATION_ERROR", f"{field} tiene un formato inválido")
    return value


def _public(err: DownstreamError) -> PublicError:
    if err.is_business:
        return PublicError(err.code, err.message)
    return PublicError("UPSTREAM_UNAVAILABLE", f"El servicio {err.service} no está disponible")


# ---------- queries ----------
async def connectors(deps: Deps, station_id: str) -> list[dict[str, Any]]:
    try:
        return await deps.clients.reservations.list_connectors(_safe_id(station_id, "stationId"))
    except DownstreamError as err:
        raise _public(err) from None


async def wallet(deps: Deps, account_id: str) -> dict[str, Any]:
    try:
        return await deps.clients.billing.get_wallet(_safe_id(account_id, "accountId"))
    except DownstreamError as err:
        raise _public(err) from None


async def saga(deps: Deps, saga_id: str) -> SagaRecord | None:
    return await deps.orchestrator.get(_safe_id(saga_id, "sagaId"))


async def sagas(deps: Deps, status: SagaStatus, limit: int) -> list[SagaRecord]:
    return await deps.orchestrator.list_by_status(status, max(1, min(limit, MAX_LIST)))


async def flags(deps: Deps) -> dict[Flag, bool]:
    return await deps.flags.all()


# ---------- mutations ----------
async def start_charge(deps: Deps, data: dict[str, Any]) -> SagaRecord:
    try:
        payload = StartChargeInput.model_validate(data)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
        raise PublicError("VALIDATION_ERROR", f"Datos inválidos: {fields}") from None
    return await deps.orchestrator.start_charge(payload)


async def set_flag(deps: Deps, headers: Mapping[str, str], name: Flag, enabled: bool) -> bool:
    who = require_admin(headers, deps.settings)
    await deps.flags.set(name, enabled, updated_by=who)
    return enabled


# ---------- suscripciones (WSS) ----------
# Cada suscripción consulta DynamoDB cada poll_interval_s y emite SOLO cuando hay cambios.
# Así funciona con varias réplicas del gateway sin necesitar un pub/sub (decisión T7).
async def watch_saga(deps: Deps, saga_id: str) -> AsyncIterator[SagaRecord]:
    saga_id = _safe_id(saga_id, "sagaId")
    last: str | None = None
    waited = 0.0
    while waited < WATCH_MAX_S:
        record = await deps.orchestrator.get(saga_id)
        if record and record.updated_at != last:
            last = record.updated_at
            yield record
            if record.status in TERMINAL_STATUSES:
                return  # la saga terminó: se cierra la suscripción
        await asyncio.sleep(deps.poll_interval_s)
        waited += deps.poll_interval_s


async def watch_flags(deps: Deps) -> AsyncIterator[dict[Flag, bool]]:
    last: dict[Flag, bool] | None = None
    while True:
        current = await deps.flags.all()
        if current != last:
            last = current
            yield current
        await asyncio.sleep(deps.poll_interval_s)


async def watch_station(deps: Deps, station_id: str) -> AsyncIterator[list[dict[str, Any]]]:
    last: list[dict[str, Any]] | None = None
    while True:
        current = await connectors(deps, station_id)
        if current != last:
            last = current
            yield current
        await asyncio.sleep(deps.poll_interval_s)
