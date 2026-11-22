"""Esquema GraphQL (Strawberry): tipos, queries, mutations y subscriptions.

Sin `from __future__ import annotations`: Strawberry necesita ver los tipos reales.
"""

import dataclasses
from collections.abc import AsyncGenerator
from typing import Any

import strawberry
from strawberry.types import Info

from . import resolvers
from .flags import Flag
from .resolvers import Deps
from .saga.models import SagaRecord, SagaStatus
from .security import extensions_for

strawberry.enum(SagaStatus, name="SagaStatus")
strawberry.enum(Flag, name="FlagName")


def _deps(info: Info) -> Deps:
    return info.context["deps"]


# ---------- tipos ----------
@strawberry.type
class StepEvent:
    step: str
    action: str
    outcome: str
    at: str
    detail: str | None


@strawberry.type
class FlagValue:
    name: Flag
    enabled: bool

    @staticmethod
    def many(values: dict[Any, bool]) -> list["FlagValue"]:
        known = {f.value for f in Flag}
        return [FlagValue(name=Flag(str(k)), enabled=v) for k, v in values.items() if k in known]


@strawberry.type
class Saga:
    saga_id: strawberry.ID
    status: SagaStatus
    station_id: str
    connector_id: str
    vehicle_id: str
    account_id: str
    energy_kwh: float
    amount_cents: int
    power_kw: float
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    history: list[StepEvent]
    flags: list[FlagValue]

    @staticmethod
    def of(r: SagaRecord) -> "Saga":
        return Saga(
            saga_id=strawberry.ID(r.saga_id),
            status=r.status,
            station_id=r.station_id,
            connector_id=r.connector_id,
            vehicle_id=r.vehicle_id,
            account_id=r.account_id,
            energy_kwh=r.energy_kwh,
            amount_cents=r.amount_cents,
            power_kw=r.power_kw,
            error_code=r.error_code,
            error_message=r.error_message,
            created_at=r.created_at,
            updated_at=r.updated_at,
            history=[
                StepEvent(
                    step=h.step.value,
                    action=h.action,
                    outcome=h.outcome,
                    at=h.at,
                    detail=h.detail,
                )
                for h in r.history
            ],
            flags=FlagValue.many(r.flags),
        )


@strawberry.type
class Connector:
    station_id: str
    connector_id: str
    power_kw: float
    status: str
    saga_id: str | None

    @staticmethod
    def of(d: dict[str, Any]) -> "Connector":
        return Connector(
            station_id=d["station_id"],
            connector_id=d["connector_id"],
            power_kw=d["power_kw"],
            status=d["status"],
            saga_id=d.get("saga_id"),
        )


@strawberry.type
class Wallet:
    account_id: str
    balance_cents: int


@strawberry.input(name="StartChargeInput")
class StartChargeInputGQL:
    station_id: str
    connector_id: str
    vehicle_id: str
    account_id: str
    energy_kwh: float
    saga_id: strawberry.ID | None = None


# ---------- operaciones ----------
@strawberry.type
class Query:
    @strawberry.field
    async def connectors(self, info: Info, station_id: str) -> list[Connector]:
        return [Connector.of(c) for c in await resolvers.connectors(_deps(info), station_id)]

    @strawberry.field
    async def wallet(self, info: Info, account_id: str) -> Wallet:
        w = await resolvers.wallet(_deps(info), account_id)
        return Wallet(account_id=w["account_id"], balance_cents=w["balance_cents"])

    @strawberry.field
    async def saga(self, info: Info, saga_id: strawberry.ID) -> Saga | None:
        record = await resolvers.saga(_deps(info), str(saga_id))
        return Saga.of(record) if record else None

    @strawberry.field
    async def sagas(self, info: Info, status: SagaStatus, limit: int = 20) -> list[Saga]:
        return [Saga.of(r) for r in await resolvers.sagas(_deps(info), status, limit)]

    @strawberry.field
    async def flags(self, info: Info) -> list[FlagValue]:
        return FlagValue.many(await resolvers.flags(_deps(info)))


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def start_charge(self, info: Info, input: StartChargeInputGQL) -> Saga:
        record = await resolvers.start_charge(_deps(info), dataclasses.asdict(input))
        return Saga.of(record)

    @strawberry.mutation
    async def set_flag(self, info: Info, name: Flag, enabled: bool) -> FlagValue:
        headers = info.context["request"].headers
        value = await resolvers.set_flag(_deps(info), headers, name, enabled)
        return FlagValue(name=name, enabled=value)


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def saga_updates(self, info: Info, saga_id: strawberry.ID) -> AsyncGenerator[Saga, None]:
        async for record in resolvers.watch_saga(_deps(info), str(saga_id)):
            yield Saga.of(record)

    @strawberry.subscription
    async def feature_flags_changed(self, info: Info) -> AsyncGenerator[list[FlagValue], None]:
        async for values in resolvers.watch_flags(_deps(info)):
            yield FlagValue.many(values)

    @strawberry.subscription
    async def station_updates(
        self, info: Info, station_id: str
    ) -> AsyncGenerator[list[Connector], None]:
        async for items in resolvers.watch_station(_deps(info), station_id):
            yield [Connector.of(c) for c in items]


def build_schema(env: str) -> strawberry.Schema:
    return strawberry.Schema(
        query=Query,
        mutation=Mutation,
        subscription=Subscription,
        extensions=extensions_for(env),
    )
