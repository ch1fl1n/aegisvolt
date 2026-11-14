"""Clientes HTTP hacia los 3 microservicios: contexto propagado, timeouts y reintentos."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from aegis_common.context import get_correlation_id

from .config import GatewaySettings


class DownstreamError(Exception):
    """Un microservicio respondió con error (status) o no respondió (status=None)."""

    def __init__(self, service: str, status: int | None, code: str, message: str) -> None:
        super().__init__(f"{service}: {status} {code} {message}")
        self.service = service
        self.status = status
        self.code = code
        self.message = message

    @property
    def is_business(self) -> bool:
        """4xx = decisión de negocio (fondos, avería, conflicto): la SAGA compensa."""
        return self.status is not None and 400 <= self.status < 500


class ServiceClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        timeout: float,
        retries: int = 2,
        backoff_s: float = 0.2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self._retries = retries
        self._backoff_s = backoff_s
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def request(
        self, method: str, path: str, *, json: Any = None, saga_id: str | None = None
    ) -> Any:
        headers = {"x-correlation-id": get_correlation_id()}
        if saga_id:
            headers["x-saga-id"] = saga_id

        for attempt in range(self._retries + 1):
            last = attempt == self._retries
            try:
                resp = await self._http.request(method, path, json=json, headers=headers)
            except httpx.TransportError as exc:  # caído, timeout, conexión rechazada
                if last:
                    raise DownstreamError(
                        self.name, None, "UNAVAILABLE", type(exc).__name__
                    ) from exc
            else:
                # Solo 5xx se reintenta: es seguro porque los endpoints son idempotentes.
                if resp.status_code < 500 or last:
                    return self._parse(resp)
            await asyncio.sleep(self._backoff_s * 2**attempt)  # 0.2 s, 0.4 s...
        raise RuntimeError("inalcanzable")

    def _parse(self, resp: httpx.Response) -> Any:
        if resp.is_success:
            return resp.json()
        try:
            err = resp.json()["error"]
            code, message = str(err["code"]), str(err["message"])
        except (ValueError, KeyError, TypeError):
            code, message = "UNKNOWN", resp.text[:200]
        raise DownstreamError(self.name, resp.status_code, code, message)

    async def aclose(self) -> None:
        await self._http.aclose()


class ReservationsClient(ServiceClient):
    async def reserve(
        self, saga_id: str, station_id: str, connector_id: str, vehicle_id: str
    ) -> dict[str, Any]:
        body = {
            "saga_id": saga_id,
            "station_id": station_id,
            "connector_id": connector_id,
            "vehicle_id": vehicle_id,
        }
        return await self.request("POST", "/reservations", json=body, saga_id=saga_id)

    async def release(self, saga_id: str, station_id: str, connector_id: str) -> dict[str, Any]:
        body = {"saga_id": saga_id, "station_id": station_id, "connector_id": connector_id}
        return await self.request("POST", "/reservations/release", json=body, saga_id=saga_id)

    async def list_connectors(self, station_id: str) -> list[dict[str, Any]]:
        return await self.request("GET", f"/stations/{station_id}/connectors")


class BillingClient(ServiceClient):
    async def charge(self, saga_id: str, account_id: str, amount_cents: int) -> dict[str, Any]:
        body = {"saga_id": saga_id, "account_id": account_id, "amount_cents": amount_cents}
        return await self.request("POST", "/charges", json=body, saga_id=saga_id)

    async def refund(self, saga_id: str, account_id: str) -> dict[str, Any]:
        body = {"saga_id": saga_id, "account_id": account_id}
        return await self.request("POST", "/charges/refund", json=body, saga_id=saga_id)

    async def get_wallet(self, account_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/wallets/{account_id}")


class DispatchClient(ServiceClient):
    async def start(
        self,
        saga_id: str,
        station_id: str,
        connector_id: str,
        vehicle_id: str,
        power_kw: float,
        fault_injection: bool,
    ) -> dict[str, Any]:
        body = {
            "saga_id": saga_id,
            "station_id": station_id,
            "connector_id": connector_id,
            "vehicle_id": vehicle_id,
            "power_kw": power_kw,
            "fault_injection": fault_injection,
        }
        return await self.request("POST", "/sessions", json=body, saga_id=saga_id)

    async def stop(self, saga_id: str) -> dict[str, Any]:
        return await self.request("POST", f"/sessions/{saga_id}/stop", saga_id=saga_id)


@dataclass
class Clients:
    reservations: ReservationsClient
    billing: BillingClient
    dispatch: DispatchClient

    async def aclose(self) -> None:
        for client in (self.reservations, self.billing, self.dispatch):
            await client.aclose()


def build_clients(
    settings: GatewaySettings, transport: httpx.AsyncBaseTransport | None = None
) -> Clients:
    timeout = settings.http_timeout_s
    return Clients(
        reservations=ReservationsClient(
            "reservations", settings.reservations_url, timeout=timeout, transport=transport
        ),
        billing=BillingClient(
            "billing", settings.billing_url, timeout=timeout, transport=transport
        ),
        dispatch=DispatchClient(
            "dispatch", settings.dispatch_url, timeout=timeout, transport=transport
        ),
    )
