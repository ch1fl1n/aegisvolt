"""Contexto por petición: correlation_id y saga_id viajan con cada log."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
saga_id_var: ContextVar[str | None] = ContextVar("saga_id", default=None)

# Solo letras, números y guiones, de 8 a 64 caracteres: evita "log injection".
_SAFE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def new_id() -> str:
    return str(uuid.uuid4())


def sanitize_id(value: str | None) -> str:
    """Devuelve el ID si es seguro; si no, genera uno nuevo."""
    if value and _SAFE_ID.fullmatch(value):
        return value
    return new_id()


def get_correlation_id() -> str:
    """El correlation_id actual (lo crea si aún no existe)."""
    current = correlation_id_var.get()
    if current is None:
        current = new_id()
        correlation_id_var.set(current)
    return current
