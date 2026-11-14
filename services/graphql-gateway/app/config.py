"""Configuración del gateway: URLs de los servicios, timeouts y tablas propias."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr

from aegis_common.config import Settings


class GatewaySettings(Settings):
    # En Kubernetes serán los Services internos (http://station-reservation-service...).
    reservations_url: str = Field(default="http://localhost:8001", alias="RESERVATIONS_URL")
    billing_url: str = Field(default="http://localhost:8002", alias="BILLING_URL")
    dispatch_url: str = Field(default="http://localhost:8003", alias="DISPATCH_URL")
    http_timeout_s: float = Field(default=3.0, gt=0, le=30, alias="HTTP_TIMEOUT_S")
    flags_cache_ttl_s: float = Field(default=5.0, ge=0, le=60, alias="FLAGS_CACHE_TTL_S")
    # Token para cambiar flags (paso 6c). SecretStr: nunca se imprime en logs.
    admin_token: SecretStr | None = Field(default=None, alias="ADMIN_TOKEN")

    @property
    def sagas_table(self) -> str:
        return self.table_name("sagas")

    @property
    def flags_table(self) -> str:
        return self.table_name("flags")


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()  # type: ignore[call-arg]
