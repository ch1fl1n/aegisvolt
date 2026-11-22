"""Clientes HTTP con un transporte falso (httpx.MockTransport): sin red real."""

import httpx
import pytest

from app.clients import DownstreamError, ServiceClient


def _client(handler) -> ServiceClient:
    return ServiceClient(
        "billing",
        "http://billing",
        timeout=1,
        retries=2,
        backoff_s=0,  # sin esperas en las pruebas
        transport=httpx.MockTransport(handler),
    )


async def test_propaga_correlation_y_saga_id():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert await client.request("POST", "/charges", json={}, saga_id="saga-1") == {"ok": True}
    assert seen[0].headers["x-saga-id"] == "saga-1"
    assert seen[0].headers["x-correlation-id"]
    await client.aclose()


async def test_4xx_es_negocio_y_no_se_reintenta():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = {"error": {"code": "INSUFFICIENT_FUNDS", "message": "Saldo insuficiente"}}
        return httpx.Response(402, json=body)

    client = _client(handler)
    with pytest.raises(DownstreamError) as info:
        await client.request("POST", "/charges", json={})
    assert (info.value.status, info.value.code) == (402, "INSUFFICIENT_FUNDS")
    assert info.value.is_business
    assert calls == 1
    await client.aclose()


async def test_5xx_se_reintenta_y_luego_funciona():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls == 1 else httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert await client.request("GET", "/x") == {"ok": True}
    assert calls == 2
    await client.aclose()


async def test_servicio_caido_es_unavailable_tras_reintentos():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("conexión rechazada", request=request)

    client = _client(handler)
    with pytest.raises(DownstreamError) as info:
        await client.request("GET", "/x")
    assert (info.value.status, info.value.code) == (None, "UNAVAILABLE")
    assert not info.value.is_business
    assert calls == 3  # 1 intento + 2 reintentos
    await client.aclose()
