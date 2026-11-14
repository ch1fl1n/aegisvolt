"""Fábrica de aplicaciones FastAPI con todo lo común ya conectado."""

from __future__ import annotations

from fastapi import FastAPI

from .config import Settings
from .errors import register_error_handlers
from .health import Check, health_router
from .logs import configure_logging
from .middleware import RequestContextMiddleware


def create_app(
    settings: Settings,
    *,
    title: str,
    readiness_checks: dict[str, Check] | None = None,
) -> FastAPI:
    configure_logging(settings)
    is_prod = settings.env == "prod"

    app = FastAPI(
        title=title,
        version=settings.service_version,
        docs_url=None if is_prod else "/docs",  # en prod no se publica el mapa de la API
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health_router(readiness_checks or {}))
    return app
