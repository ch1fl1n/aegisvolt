"""Casos de uso del servicio: lo que el resto del sistema puede pedirle."""

from __future__ import annotations

import logging

from .models import (
    Connector,
    ConnectorIn,
    ReleaseRequest,
    ReleaseResult,
    ReservationRequest,
)
from .repository import ReservationRepository

log = logging.getLogger("reservations")


class ReservationService:
    def __init__(self, repo: ReservationRepository) -> None:
        self._repo = repo

    # ---------- inventario ----------
    def list_connectors(self, station_id: str) -> list[Connector]:
        return self._repo.list_connectors(station_id)

    def register_connector(
        self, station_id: str, connector_id: str, data: ConnectorIn
    ) -> Connector:
        connector = self._repo.put_connector(station_id, connector_id, data)
        log.info(
            "Conector registrado",
            extra={
                "event": "connector_registered",
                "station_id": station_id,
                "connector_id": connector_id,
                "connector_status": connector.status.value,
            },
        )
        return connector

    def find_by_saga(self, saga_id: str) -> list[Connector]:
        return self._repo.find_by_saga(saga_id)

    # ---------- SAGA ----------
    def reserve(self, req: ReservationRequest) -> Connector:
        """Paso 1 de la SAGA. Los errores (409/422/404) los lanza el repositorio."""
        connector = self._repo.reserve(req)
        log.info(
            "Conector reservado",
            extra={
                "event": "saga_step",
                "step": "reserve_connector",
                "outcome": "ok",
                "station_id": req.station_id,
                "connector_id": req.connector_id,
            },
        )
        return connector

    def release(self, req: ReleaseRequest) -> ReleaseResult:
        """Compensación del paso 1. Idempotente: liberar dos veces no es error."""
        released = self._repo.release(req)
        log.info(
            "Compensación: liberar conector",
            extra={
                "event": "saga_step",
                "step": "release_connector",
                "outcome": "released" if released else "noop",
                "station_id": req.station_id,
                "connector_id": req.connector_id,
            },
        )
        return ReleaseResult(saga_id=req.saga_id, released=released)
