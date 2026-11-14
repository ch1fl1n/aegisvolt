"""Configuración del servicio: la común de aegis_common + lo propio de dispatch."""

from __future__ import annotations

from functools import lru_cache

from aegis_common.config import Settings


class DispatchSettings(Settings):
    @property
    def table(self) -> str:
        """aegisvolt-dispatch-<env>: la ÚNICA tabla que toca este servicio."""
        return self.table_name("dispatch")

    @property
    def allow_fault_injection(self) -> bool:
        """Nunca en prod: una flag mal puesta no puede simular averías con clientes reales."""
        return self.env != "prod"


@lru_cache
def get_settings() -> DispatchSettings:
    return DispatchSettings()  # type: ignore[call-arg]
