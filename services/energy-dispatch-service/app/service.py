"""Casos de uso del servicio: iniciar y detener sesiones de carga."""

from __future__ import annotations

import logging

from aegis_common.errors import AegisError, ChargerFaultError, NotFoundError

from .models import Session, SessionStatus, StartRequest, StopResult
from .repository import DispatchRepository

log = logging.getLogger("dispatch")


class FaultInjectionDisabledError(AegisError):
    """Se pidió simular una avería en un ambiente donde está prohibido (prod)."""

    status_code = 403
    code = "FAULT_INJECTION_DISABLED"


class DispatchService:
    def __init__(self, repo: DispatchRepository, *, allow_fault_injection: bool) -> None:
        self._repo = repo
        self._allow_fault_injection = allow_fault_injection

    def get(self, saga_id: str) -> Session:
        session = self._repo.get(saga_id)
        if session is None:
            raise NotFoundError("Sesión no existe", details={"saga_id": saga_id})
        return session

    # ---------- SAGA ----------
    def start(self, req: StartRequest) -> Session:
        """Paso 3 de la SAGA. Una sesión FAULTED se guarda y luego se responde 422."""
        if req.fault_injection and not self._allow_fault_injection:
            raise FaultInjectionDisabledError("Simulación de fallas deshabilitada en este ambiente")

        session = self._repo.start(req, fault=req.fault_injection)
        faulted = session.status is SessionStatus.FAULTED
        log.log(
            logging.WARNING if faulted else logging.INFO,
            "Inicio de carga",
            extra={
                "event": "saga_step",
                "step": "start_charging",
                "outcome": "faulted" if faulted else "ok",
                "station_id": req.station_id,
                "connector_id": req.connector_id,
                "power_kw": req.power_kw,
            },
        )
        if faulted:
            raise ChargerFaultError(
                "El cargador reportó una falla de hardware", details={"saga_id": req.saga_id}
            )
        return session

    def stop(self, saga_id: str) -> StopResult:
        """Compensación del paso 3 (o fin normal). Idempotente."""
        stopped = self._repo.stop(saga_id)
        log.info(
            "Detener carga",
            extra={
                "event": "saga_step",
                "step": "stop_charging",
                "outcome": "stopped" if stopped else "noop",
            },
        )
        return StopResult(saga_id=saga_id, stopped=stopped)
