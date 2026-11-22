"""Punto de entrada: uvicorn app.main:build --factory"""

from __future__ import annotations

from fastapi import FastAPI

from aegis_common import aws
from aegis_common.health import dynamodb_table_check
from aegis_common.web import create_app

from .config import ReservationSettings, get_settings
from .repository import ReservationRepository
from .routes import router
from .service import ReservationService


def build(
    settings: ReservationSettings | None = None,
    service: ReservationService | None = None,
) -> FastAPI:
    """Arma la app. En pruebas se inyecta un service con repositorio falso."""
    settings = settings or get_settings()
    if service is None:
        table = aws.resource("dynamodb", settings).Table(settings.table)
        service = ReservationService(ReservationRepository(table))

    app = create_app(
        settings,
        title="station-reservation-service",
        readiness_checks={
            "dynamodb": dynamodb_table_check(aws.client("dynamodb", settings), settings.table)
        },
    )
    app.state.service = service
    app.include_router(router)
    return app
