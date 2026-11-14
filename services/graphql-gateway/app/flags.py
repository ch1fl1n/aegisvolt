"""Feature flags propias en DynamoDB (una tabla por ambiente) con caché de 5 s."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import anyio


class Flag(StrEnum):
    DYNAMIC_SURGE_PRICING = "ENABLE_DYNAMIC_SURGE_PRICING"
    FAST_CHARGE_BOOST = "ENABLE_FAST_CHARGE_BOOST"
    SIMULATE_CHARGER_FAULT = "SIMULATE_CHARGER_HARDWARE_FAULT"


# Flag ausente en la tabla = apagada (el comportamiento seguro por defecto).
DEFAULTS: dict[Flag, bool] = dict.fromkeys(Flag, False)


class FlagStore:
    def __init__(
        self,
        table: Any,
        *,
        ttl_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._table = table
        self._ttl_s = ttl_s
        self._clock = clock  # inyectable: las pruebas controlan el paso del tiempo
        self._cache: dict[Flag, bool] | None = None
        self._loaded_at = 0.0

    def _load(self) -> dict[Flag, bool]:
        """Lee la tabla completa (son pocas filas). Ignora nombres desconocidos."""
        values = dict(DEFAULTS)
        kwargs: dict[str, Any] = {}
        while True:
            page = self._table.scan(**kwargs)
            for item in page.get("Items", []):
                name = item.get("flag_name")
                if name in Flag.__members__.values():
                    values[Flag(name)] = bool(item.get("enabled", False))
            if "LastEvaluatedKey" not in page:
                return values
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    async def all(self) -> dict[Flag, bool]:
        fresh = self._cache is not None and self._clock() - self._loaded_at < self._ttl_s
        if not fresh:
            # boto3 bloquea: se ejecuta en un hilo para no congelar el event loop.
            self._cache = await anyio.to_thread.run_sync(self._load)
            self._loaded_at = self._clock()
        assert self._cache is not None  # noqa: S101 (solo para el type checker)
        return dict(self._cache)

    async def is_enabled(self, flag: Flag) -> bool:
        return (await self.all())[flag]

    async def set(self, flag: Flag, enabled: bool, *, updated_by: str) -> None:
        item = {
            "flag_name": flag.value,
            "enabled": enabled,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "updated_by": updated_by,
        }
        await anyio.to_thread.run_sync(lambda: self._table.put_item(Item=item))
        self._cache = None  # esta réplica lo ve al instante; las demás en <= ttl_s
