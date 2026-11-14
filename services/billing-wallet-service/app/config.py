"""Configuración del servicio: la común de aegis_common + lo propio de billing."""

from __future__ import annotations

from functools import lru_cache

from aegis_common.config import Settings


class BillingSettings(Settings):
    @property
    def table(self) -> str:
        """aegisvolt-billing-<env>: la ÚNICA tabla que toca este servicio."""
        return self.table_name("billing")


@lru_cache
def get_settings() -> BillingSettings:
    return BillingSettings()  # type: ignore[call-arg]
