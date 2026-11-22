"""Orquestador: ejecuta los pasos en orden y, si uno falla, compensa en orden inverso."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from aegis_common.context import new_id, saga_id_var

from ..clients import Clients, DownstreamError
from ..flags import FlagStore
from .models import SagaRecord, SagaStatus, StartChargeInput, StepRecord
from .repository import SagaAlreadyExistsError, SagaRepository
from .steps import STEPS, Step, quote

log = logging.getLogger("saga")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class SagaOrchestrator:
    def __init__(
        self,
        repo: SagaRepository,
        clients: Clients,
        flags: FlagStore,
        *,
        steps: tuple[Step, ...] = STEPS,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self._repo = repo
        self._clients = clients
        self._flags = flags
        self._steps = steps
        self._new_id = id_factory

    async def get(self, saga_id: str) -> SagaRecord | None:
        return await self._repo.get(saga_id)

    async def list_by_status(self, status: SagaStatus, limit: int) -> list[SagaRecord]:
        return await self._repo.list_by_status(status, limit)

    async def start_charge(self, data: StartChargeInput) -> SagaRecord:
        """Ejecuta la saga completa. Si el saga_id ya existe, devuelve esa (idempotente)."""
        if data.saga_id:
            existing = await self._repo.get(data.saga_id)
            if existing:
                return existing

        # Flag es StrEnum: str(flag) == su nombre en la tabla ("ENABLE_FAST_CHARGE_BOOST").
        flags = {str(flag): on for flag, on in (await self._flags.all()).items()}
        amount_cents, power_kw = quote(data.energy_kwh, flags)
        now = _now()
        record = SagaRecord(
            saga_id=data.saga_id or self._new_id(),
            status=SagaStatus.STARTED,
            **data.model_dump(exclude={"saga_id"}),
            amount_cents=amount_cents,
            power_kw=power_kw,
            flags=flags,
            created_at=now,
            updated_at=now,
        )
        token = saga_id_var.set(record.saga_id)  # todos los logs llevan el saga_id
        try:
            try:
                await self._repo.create(record)
            except SagaAlreadyExistsError:  # carrera: otra petición la creó un instante antes
                existing = await self._repo.get(record.saga_id)
                if existing is None:
                    raise
                return existing
            log.info(
                "Saga iniciada",
                extra={"event": "saga_started", "flags": flags, "amount_cents": amount_cents},
            )
            await self._run(record)
        finally:
            saga_id_var.reset(token)
        return record

    async def _run(self, record: SagaRecord) -> None:
        attempted: list[Step] = []
        for step in self._steps:
            attempted.append(step)
            try:
                await step.action(record, self._clients)
            except DownstreamError as err:
                self._note(record, step, "do", "error", f"{err.status} {err.code}")
                record.error_code, record.error_message = err.code, err.message
                await self._compensate(record, attempted)
                return
            self._note(record, step, "do", "ok")
            record.status = step.done_status
            await self._save(record)
        log.info("Saga completada", extra={"event": "saga_finished", "outcome": "completed"})

    async def _compensate(self, record: SagaRecord, attempted: list[Step]) -> None:
        """Deshace TODO lo intentado (incluido el paso que falló: pudo aplicarse
        antes de un timeout). Es seguro porque cada compensación es idempotente."""
        record.status = SagaStatus.COMPENSATING
        await self._save(record)
        all_ok = True
        for step in reversed(attempted):
            try:
                await step.compensation(record, self._clients)
            except DownstreamError as err:
                all_ok = False
                self._note(record, step, "compensate", "error", f"{err.status} {err.code}")
            else:
                self._note(record, step, "compensate", "ok")
        record.status = SagaStatus.COMPENSATED if all_ok else SagaStatus.FAILED
        await self._save(record)
        log.log(
            logging.WARNING if all_ok else logging.ERROR,
            "Saga compensada" if all_ok else "Saga FALLIDA: compensación incompleta",
            extra={
                "event": "saga_finished",
                "outcome": record.status.value.lower(),
                "code": record.error_code,
            },
        )

    def _note(
        self,
        record: SagaRecord,
        step: Step,
        action: Literal["do", "compensate"],
        outcome: Literal["ok", "error"],
        detail: str | None = None,
    ) -> None:
        record.history.append(
            StepRecord(step=step.name, action=action, outcome=outcome, at=_now(), detail=detail)
        )

    async def _save(self, record: SagaRecord) -> None:
        record.updated_at = _now()
        await self._repo.save(record)
