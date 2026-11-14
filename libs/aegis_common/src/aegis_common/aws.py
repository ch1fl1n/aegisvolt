"""Clientes de AWS con reintentos y timeouts (sirve igual para Floci y AWS real)."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config

from .config import Settings

# Reintentos con backoff ante errores transitorios; timeouts cortos para no colgar peticiones.
_BOTO_CONFIG = Config(
    retries={"max_attempts": 3, "mode": "standard"},
    connect_timeout=2,
    read_timeout=5,
)


def client(service: str, settings: Settings) -> Any:
    return boto3.client(
        service,
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        config=_BOTO_CONFIG,
    )


def resource(service: str, settings: Settings) -> Any:
    return boto3.resource(
        service,
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        config=_BOTO_CONFIG,
    )
