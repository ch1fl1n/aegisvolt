"""Pruebas del middleware, los errores y la salud (no necesitan Floci)."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aegis_common.config import get_settings
from aegis_common.errors import InsufficientFundsError
from aegis_common.web import create_app

CID = "abcd1234-0000-1111-2222-333344445555"


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("AEGIS_ENV", "test")
    monkeypatch.setenv("SERVICE_NAME", "demo-service")
    monkeypatch.delenv("CLOUDWATCH_LOGS_ENABLED", raising=False)
    get_settings.cache_clear()

    state = {"ready": True}

    def check() -> None:
        if not state["ready"]:
            raise RuntimeError("secreto interno de la base")

    app = create_app(get_settings(), title="demo", readiness_checks={"db": check})

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/fondos")
    def fondos() -> None:
        raise InsufficientFundsError("Saldo insuficiente", details={"balance": 10})

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("detalle interno que no debe salir")

    app.state.readiness = state
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_correlation_id_valido_se_devuelve(client: TestClient) -> None:
    r = client.get("/ok", headers={"x-correlation-id": CID})
    assert r.headers["x-correlation-id"] == CID


def test_correlation_id_malicioso_se_reemplaza(client: TestClient) -> None:
    r = client.get("/ok", headers={"x-correlation-id": "<script>alert(1)</script>"})
    assert r.headers["x-correlation-id"] != "<script>alert(1)</script>"
    assert len(r.headers["x-correlation-id"]) == 36


def test_error_de_negocio_formato_uniforme(client: TestClient) -> None:
    r = client.get("/fondos", headers={"x-correlation-id": CID})
    body = r.json()["error"]
    assert r.status_code == 402
    assert body["code"] == "INSUFFICIENT_FUNDS"
    assert body["details"] == {"balance": 10}
    assert body["correlation_id"] == CID


def test_error_inesperado_no_filtra_detalles(client: TestClient) -> None:
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "detalle interno" not in r.text


def test_readiness(client: TestClient, app: FastAPI) -> None:
    assert client.get("/readyz").status_code == 200
    app.state.readiness["ready"] = False
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["db"] == "error: RuntimeError"
    assert "secreto" not in r.text


def test_log_http_request_y_sondas_excluidas(client: TestClient) -> None:
    handler = ListHandler()
    logging.getLogger().addHandler(handler)
    try:
        client.get("/ok")
        client.get("/healthz")
    finally:
        logging.getLogger().removeHandler(handler)

    requests = [r for r in handler.records if getattr(r, "event", None) == "http_request"]
    assert [(r.path, r.status) for r in requests] == [("/ok", 200)]
