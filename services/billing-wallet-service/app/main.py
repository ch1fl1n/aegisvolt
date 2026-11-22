"""Punto de entrada: uvicorn app.main:build --factory"""

from __future__ import annotations

from fastapi import FastAPI

from aegis_common import aws
from aegis_common.health import dynamodb_table_check
from aegis_common.web import create_app

from .config import BillingSettings, get_settings
from .repository import BillingRepository
from .routes import router
from .service import BillingService


def build(
    settings: BillingSettings | None = None,
    service: BillingService | None = None,
) -> FastAPI:
    """Arma la app. En pruebas se inyecta un service con repositorio falso."""
    settings = settings or get_settings()
    if service is None:
        table = aws.resource("dynamodb", settings).Table(settings.table)
        service = BillingService(BillingRepository(table))

    app = create_app(
        settings,
        title="billing-wallet-service",
        readiness_checks={
            "dynamodb": dynamodb_table_check(aws.client("dynamodb", settings), settings.table)
        },
    )
    app.state.service = service
    app.include_router(router)
    return app
