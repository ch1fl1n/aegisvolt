"""Lo que necesita el canary: header de versión y falla inducida (bloqueada en prod)."""

import pytest
from fastapi.testclient import TestClient
from test_graphql import FakeOrchestrator, _app

QUERY = {"query": "{ flags { name } }"}


def test_cada_respuesta_dice_su_version(monkeypatch):
    monkeypatch.setenv("SERVICE_VERSION", "v2")
    client = TestClient(_app(monkeypatch, "dev", FakeOrchestrator()))
    assert client.post("/graphql", json=QUERY).headers["x-service-version"] == "v2"


@pytest.mark.parametrize(("env", "expected"), [("dev", 500), ("prod", 200)])
def test_falla_inducida_solo_fuera_de_prod(monkeypatch, env, expected):
    monkeypatch.setenv("CHAOS_ERROR_RATE", "1")  # 100 % de errores si está permitido
    client = TestClient(_app(monkeypatch, env, FakeOrchestrator()))
    assert client.post("/graphql", json=QUERY).status_code == expected
    assert client.get("/healthz").status_code == 200  # las sondas nunca fallan por chaos
