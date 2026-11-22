"""Punto de entrada: uvicorn app.main:build --factory --port 8000"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from strawberry.fastapi import GraphQLRouter

from aegis_common import aws
from aegis_common.health import dynamodb_table_check
from aegis_common.web import create_app

from .clients import build_clients
from .config import GatewaySettings, get_settings
from .flags import FlagStore
from .resolvers import Deps
from .saga.orchestrator import SagaOrchestrator
from .saga.repository import SagaRepository
from .schema import build_schema


def build_deps(settings: GatewaySettings) -> Deps:
    ddb = aws.resource("dynamodb", settings)
    flags = FlagStore(ddb.Table(settings.flags_table), ttl_s=settings.flags_cache_ttl_s)
    clients = build_clients(settings)
    sagas = SagaRepository(ddb.Table(settings.sagas_table))
    return Deps(
        settings=settings,
        clients=clients,
        flags=flags,
        orchestrator=SagaOrchestrator(sagas, clients, flags),
    )


def chaos_dependency(rate: float) -> Callable[[], Awaitable[None]]:
    """Responde 500 en una fracción `rate` de peticiones. Corre DENTRO del middleware,
    así cada 500 queda en el log http_request y el canary lo cuenta como error."""

    async def chaos() -> None:
        if rate > 0 and random.random() < rate:  # noqa: S311 (no es criptografía)
            raise HTTPException(status_code=500, detail="Falla inducida (CHAOS_ERROR_RATE)")

    return chaos


def build(settings: GatewaySettings | None = None, deps: Deps | None = None) -> FastAPI:
    """Arma la app. En pruebas se inyectan dependencias falsas."""
    settings = settings or get_settings()
    resolved = deps or build_deps(settings)

    ddb_client = aws.client("dynamodb", settings)
    app = create_app(
        settings,
        title="graphql-gateway",
        # Solo dependencias PROPIAS: si billing se cae, el gateway sigue "ready" y
        # responde UPSTREAM_UNAVAILABLE en vez de que Kubernetes lo saque de servicio.
        readiness_checks={
            "sagas_table": dynamodb_table_check(ddb_client, settings.sagas_table),
            "flags_table": dynamodb_table_check(ddb_client, settings.flags_table),
        },
    )

    async def get_context() -> dict[str, Any]:
        return {"deps": resolved}  # Strawberry agrega "request" (HTTP o WebSocket)

    graphql = GraphQLRouter(
        build_schema(settings.env),
        context_getter=get_context,
        graphql_ide=None if settings.env == "prod" else "graphiql",
        allow_queries_via_get=False,  # solo POST: nada de consultas en URLs (logs, caché)
        dependencies=[Depends(chaos_dependency(settings.effective_chaos_rate))],
    )
    app.include_router(graphql, prefix="/graphql")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved.clients.aclose()  # cierra las conexiones HTTP al apagar

    app.router.lifespan_context = lifespan
    return app
