"""Los 3 pasos de la SAGA, cada uno con su compensación, y el cálculo de precio."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..clients import Clients
from ..flags import Flag
from .models import SagaRecord, SagaStatus, StepName

BASE_PRICE_CENTS_PER_KWH = 80
SURGE_MULTIPLIER = 1.5
BASE_POWER_KW = 50.0
BOOST_POWER_KW = 150.0

StepFn = Callable[[SagaRecord, Clients], Awaitable[Any]]


def quote(energy_kwh: float, flags: dict[str, bool]) -> tuple[int, float]:
    """Precio total en centavos y potencia, según las flags vigentes."""
    price = float(BASE_PRICE_CENTS_PER_KWH)
    if flags.get(Flag.ENABLE_DYNAMIC_SURGE_PRICING.value, False):
        price *= SURGE_MULTIPLIER
    boost = flags.get(Flag.ENABLE_FAST_CHARGE_BOOST.value, False)
    power = BOOST_POWER_KW if boost else BASE_POWER_KW
    return round(energy_kwh * price), power


@dataclass(frozen=True)
class Step:
    name: StepName
    done_status: SagaStatus
    action: StepFn
    compensation: StepFn


async def _reserve(r: SagaRecord, c: Clients) -> Any:
    return await c.reservations.reserve(r.saga_id, r.station_id, r.connector_id, r.vehicle_id)


async def _release(r: SagaRecord, c: Clients) -> Any:
    return await c.reservations.release(r.saga_id, r.station_id, r.connector_id)


async def _charge(r: SagaRecord, c: Clients) -> Any:
    return await c.billing.charge(r.saga_id, r.account_id, r.amount_cents)


async def _refund(r: SagaRecord, c: Clients) -> Any:
    return await c.billing.refund(r.saga_id, r.account_id)


async def _start(r: SagaRecord, c: Clients) -> Any:
    fault = r.flags.get(Flag.SIMULATE_CHARGER_HARDWARE_FAULT.value, False)
    return await c.dispatch.start(
        r.saga_id, r.station_id, r.connector_id, r.vehicle_id, r.power_kw, fault
    )


async def _stop(r: SagaRecord, c: Clients) -> Any:
    return await c.dispatch.stop(r.saga_id)


STEPS: tuple[Step, ...] = (
    Step(StepName.RESERVE_CONNECTOR, SagaStatus.RESERVED, _reserve, _release),
    Step(StepName.CHARGE_WALLET, SagaStatus.CHARGED, _charge, _refund),
    Step(StepName.START_CHARGING, SagaStatus.COMPLETED, _start, _stop),
)
