"""API HTTP con un repositorio falso: fallo de cargador, bloqueo en prod e idempotencia."""

import pytest
from fastapi.testclient import TestClient

from aegis_common.config import get_settings as common_settings
from app.config import DispatchSettings, get_settings
from app.main import build
from app.models import Session, SessionStatus
from app.service import DispatchService

SAGA = "saga-0001"
START = {
    "saga_id": SAGA,
    "station_id": "st-1",
    "connector_id": "c1",
    "vehicle_id": "veh-1",
    "power_kw": 50,
}


class StubRepo:
    """Imita al repositorio: guarda en memoria la última sesión creada."""

    def __init__(self) -> None:
        self.session: Session | None = None
        self.stopped = True

    def start(self, req, *, fault):
        self.session = Session(
            saga_id=req.saga_id,
            station_id=req.station_id,
            connector_id=req.connector_id,
            vehicle_id=req.vehicle_id,
            power_kw=req.power_kw,
            status=SessionStatus.FAULTED if fault else SessionStatus.ACTIVE,
            started_at="2026-11-14T00:00:00+00:00",
        )
        return self.session

    def stop(self, saga_id):
        return self.stopped

    def get(self, saga_id):
        return self.session


def _client(monkeypatch: pytest.MonkeyPatch, repo: StubRepo, env: str) -> TestClient:
    monkeypatch.setenv("AEGIS_ENV", env)
    monkeypatch.setenv("SERVICE_NAME", "energy-dispatch-service")
    monkeypatch.delenv("CLOUDWATCH_LOGS_ENABLED", raising=False)
    get_settings.cache_clear()
    common_settings.cache_clear()
    settings = DispatchSettings()  # type: ignore[call-arg]
    service = DispatchService(
        repo,  # type: ignore[arg-type]
        allow_fault_injection=settings.allow_fault_injection,
    )
    return TestClient(build(settings, service=service))


@pytest.fixture
def repo() -> StubRepo:
    return StubRepo()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, repo: StubRepo) -> TestClient:
    return _client(monkeypatch, repo, "test")


def test_inicio_ok(client):
    r = client.post("/sessions", json=START)
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"


def test_falla_de_cargador_es_422_y_queda_guardada(client, repo):
    r = client.post("/sessions", json={**START, "fault_injection": True})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CHARGER_FAULT"
    assert repo.session is not None
    assert repo.session.status is SessionStatus.FAULTED


def test_simular_falla_en_prod_es_403(monkeypatch, repo):
    client = _client(monkeypatch, repo, "prod")
    r = client.post("/sessions", json={**START, "fault_injection": True})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FAULT_INJECTION_DISABLED"
    assert repo.session is None  # ni siquiera llegó a la tabla


def test_potencia_fuera_de_rango_es_rechazada(client):
    r = client.post("/sessions", json={**START, "power_kw": 1_000})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_stop_idempotente(client, repo):
    repo.stopped = False  # ya estaba detenida
    r = client.post(f"/sessions/{SAGA}/stop")
    assert r.status_code == 200
    assert r.json() == {"saga_id": SAGA, "stopped": False}


def test_sesion_inexistente_es_404(client):
    r = client.get(f"/sessions/{SAGA}")
    assert r.status_code == 404
