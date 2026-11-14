"""Configuración del servicio: la común de aegis_common + lo propio de reservas."""

from __future__ import annotations

from functools import lru_cache

from aegis_common.config import Settings


class ReservationSettings(Settings):
    @property
    def table(self) -> str:
        """aegisvolt-reservations-<env>: la ÚNICA tabla que toca este servicio."""
        return self.table_name("reservations")


@lru_cache
def get_settings() -> ReservationSettings:
    return ReservationSettings()  # type: ignore[call-arg]
