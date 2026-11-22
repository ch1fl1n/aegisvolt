"""Errores de dominio y respuesta JSON uniforme (sin filtrar detalles internos)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .context import correlation_id_var, get_correlation_id

log = logging.getLogger("aegis.errors")


class AegisError(Exception):
    """Error esperado del negocio: se responde con su código HTTP y un código legible."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AegisError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AegisError):
    """Estado incompatible, p. ej. reservar un conector que ya está RESERVED."""

    status_code = 409
    code = "CONFLICT"


class InsufficientFundsError(AegisError):
    status_code = 402
    code = "INSUFFICIENT_FUNDS"


class ChargerFaultError(AegisError):
    """Fallo físico del cargador. 422 (negocio), NO 5xx: no debe disparar el rollback del canary."""

    status_code = 422
    code = "CHARGER_FAULT"


def _request_cid(request: Request) -> str:
    """El id guardado por el middleware en request.state; si no hay, el del contexto."""
    return getattr(request.state, "correlation_id", None) or get_correlation_id()


def _response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    cid = _request_cid(request)
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "correlation_id": cid,
        }
    }
    # Argumentos CON NOMBRE: el 1er posicional de JSONResponse es content, no status_code.
    return JSONResponse(status_code=status_code, content=body, headers={"x-correlation-id": cid})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AegisError)
    async def _aegis(request: Request, exc: AegisError) -> JSONResponse:
        log.warning(exc.message, extra={"event": "business_error", "code": exc.code})
        return _response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Se omite "input": no devolvemos al cliente lo que nos mandó (evita reflejar datos).
        errors = [{k: e[k] for k in ("loc", "msg", "type") if k in e} for e in exc.errors()]
        return _response(request, 422, "VALIDATION_ERROR", "Datos inválidos", {"errors": errors})

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Corre fuera del middleware: reponemos el id para que el log lo lleve, y luego lo quitamos.
        token = correlation_id_var.set(_request_cid(request))
        try:
            log.exception("Error inesperado", extra={"event": "unhandled_error"})
            return _response(
                request, 500, "INTERNAL_ERROR", "Error interno. Usa el correlation_id."
            )
        finally:
            correlation_id_var.reset(token)
