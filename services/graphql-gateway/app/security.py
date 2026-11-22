"""Seguridad de la API GraphQL: límites de consulta, errores enmascarados y token admin."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from typing import Any

from graphql import GraphQLError
from strawberry.extensions import (
    DisableIntrospection,
    MaskErrors,
    MaxAliasesLimiter,
    MaxTokensLimiter,
    QueryDepthLimiter,
)

from .config import GatewaySettings

MAX_DEPTH = 6  # la consulta más profunda legítima (saga -> history -> step) usa 3
MAX_ALIASES = 15  # evita "alias bombing": pedir 1000 veces el mismo campo con alias
MAX_TOKENS = 2_000  # evita documentos gigantes que solo sirven para gastar CPU


class PublicError(Exception):
    """Error que SÍ se muestra al cliente, con un código estable en extensions.code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.extensions = {"code": code}  # graphql-core lo copia al error de la respuesta


def _should_mask(error: GraphQLError) -> bool:
    """Se oculta todo error inesperado (bug, excepción de boto3...). Los de sintaxis o
    validación de la consulta no tienen original_error y son culpa del cliente: se muestran."""
    original = error.original_error
    return original is not None and not isinstance(original, PublicError)


def extensions_for(env: str) -> list[Any]:
    """Fábricas (no instancias): Strawberry crea una extensión nueva por petición."""
    extensions: list[Any] = [
        lambda: QueryDepthLimiter(max_depth=MAX_DEPTH),
        lambda: MaxAliasesLimiter(max_alias_count=MAX_ALIASES),
        lambda: MaxTokensLimiter(max_token_count=MAX_TOKENS),
        lambda: MaskErrors(
            should_mask_error=_should_mask,
            error_message="Error interno. Usa el x-correlation-id de la respuesta para rastrearlo.",
        ),
    ]
    if env == "prod":
        extensions.append(DisableIntrospection)  # en prod no se publica el mapa de la API
    return extensions


def require_admin(headers: Mapping[str, str], settings: GatewaySettings) -> str:
    """Valida el header x-admin-token. compare_digest: tiempo constante (sin timing attack)."""
    expected = settings.admin_token
    received = headers.get("x-admin-token", "")
    if expected is None or not hmac.compare_digest(
        received.encode(), expected.get_secret_value().encode()
    ):
        raise PublicError("FORBIDDEN", "Se requiere un token de administración válido")
    return "admin"
