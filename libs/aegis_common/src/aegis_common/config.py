"""Configuración tipada leída de variables de entorno (12-factor, fail-fast)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["dev", "test", "prod"]


class Settings(BaseSettings):
    """Si falta una variable obligatoria o tiene un valor inválido, el servicio NO arranca."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    project: str = Field(default="aegisvolt", alias="AEGIS_PROJECT")
    env: Env = Field(alias="AEGIS_ENV")
    service_name: str = Field(alias="SERVICE_NAME")
    service_version: str = Field(default="v1", alias="SERVICE_VERSION")
    aws_region: str = Field(default="us-east-1", alias="AWS_DEFAULT_REGION")
    aws_endpoint_url: str | None = Field(default=None, alias="AWS_ENDPOINT_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cloudwatch_logs: bool = Field(default=False, alias="CLOUDWATCH_LOGS_ENABLED")

    def table_name(self, service: str) -> str:
        """Nombre de la tabla DynamoDB de un servicio en ESTE ambiente."""
        return f"{self.project}-{service}-{self.env}"

    @property
    def log_group(self) -> str:
        """Log group de CloudWatch de este servicio: /aegisvolt/<env>/<servicio>."""
        return f"/{self.project}/{self.env}/{self.service_name}"


@lru_cache
def get_settings() -> Settings:
    """Se lee una sola vez por proceso."""
    return Settings()  # type: ignore[call-arg]
