"""Middleware ASGI: correlation_id por petición + log http_request (base del canary)."""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .context import correlation_id_var, saga_id_var, sanitize_id

log = logging.getLogger("aegis.http")

# Las sondas de Kubernetes no cuentan como tráfico real (no inflan el canary).
_NOT_LOGGED = {"/healthz", "/readyz"}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, version: str | None = None) -> None:
        self.app = app
        self.version = version  # se devuelve en x-service-version (se ve el reparto canary)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # websockets y lifespan pasan sin tocar
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        correlation_id = sanitize_id(headers.get("x-correlation-id"))
        raw_saga = headers.get("x-saga-id")
        saga_id = sanitize_id(raw_saga) if raw_saga else None
        # request.state sobrevive al middleware: lo usa el handler de 500.
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        cid_token = correlation_id_var.set(correlation_id)
        saga_token = saga_id_var.set(saga_id)
        status: dict[str, Any] = {"code": 500}  # si algo explota antes de responder => 500
        started = time.perf_counter()

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers.append("x-correlation-id", correlation_id)
                if self.version:
                    response_headers.append("x-service-version", self.version)
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            path = scope.get("path", "")
            if path not in _NOT_LOGGED:
                log.info(
                    "%s %s -> %s",
                    scope.get("method"),
                    path,
                    status["code"],
                    extra={
                        "event": "http_request",
                        "method": scope.get("method"),
                        "path": path,
                        "status": status["code"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            correlation_id_var.reset(cid_token)
            saga_id_var.reset(saga_token)
