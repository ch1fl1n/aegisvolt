"""API HTTP con un repositorio falso: valida rutas, códigos y formato de error (sin Floci)."""

import pytest
from fastapi.testclient import TestClient

from aegis_common.config import get_settings as common_settings
from aegis_common.errors import AegisError, ChargerFaultError, ConflictError
from app.config import ReservationSettings, get_settings
from app.main import build
from app.models import Connector, ConnectorStatus
from app.service import ReservationService

SAGA = "saga-0001"
BODY = {"saga_id": SAGA, "station_id": "st-1", "connector_id": "c1", "vehicle_id": "veh-1"}


def _connector(status: ConnectorStatus = ConnectorStatus.AVAILABLE, **kw) -> Connector:
    return Connector(station_id="st-1", connector_id="c1", power_kw=50, status=status, **kw)


class StubRepo:
    """Imita al repositorio: devuelve datos fijos o lanza el error que se le indique."""

    def __init__(self) -> None:
        self.error: AegisError | None = None
        self.released = True

    def reserve(self, req):
        if self.error:
            raise self.error
        return _connector(ConnectorStatus.RESERVED, saga_id=req.saga_id, vehicle_id=req.vehicle_id)

    def release(self, req):
        return self.released

    def list_connectors(self, station_id):
        return [_connector()]

    def put_connector(self, station_id, connector_id, data):
        return _connector(data.status)

    def find_by_saga(self, saga_id):
        return []


@pytest.fixture
def repo() -> StubRepo:
    return StubRepo()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, repo: StubRepo) -> TestClient:
    monkeypatch.setenv("AEGIS_ENV", "test")
    monkeypatch.setenv("SERVICE_NAME", "station-reservation-service")
    monkeypatch.delenv("CLOUDWATCH_LOGS_ENABLED", raising=False)
    get_settings.cache_clear()
    common_settings.cache_clear()
    settings = ReservationSettings()  # type: ignore[call-arg]
    app = build(settings, service=ReservationService(repo))  # type: ignore[arg-type]
    return TestClient(app)


def test_reserva_ok(client):
    r = client.post("/reservations", json=BODY)
    assert r.status_code == 200
    assert r.json()["status"] == "RESERVED"
    assert r.json()["saga_id"] == SAGA


def test_conflicto_es_409_con_formato_uniforme(client, repo):
    repo.error = ConflictError("El conector no está disponible")
    r = client.post("/reservations", json=BODY)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_averia_es_422_no_5xx(client, repo):
    repo.error = ChargerFaultError("El conector está averiado")
    r = client.post("/reservations", json=BODY)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CHARGER_FAULT"


def test_id_invalido_es_rechazado(client):
    r = client.post("/reservations", json={**BODY, "connector_id": "c1; DROP"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_compensacion_idempotente(client, repo):
    repo.released = False  # ya estaba libre
    r = client.post("/reservations/release", json={k: BODY[k] for k in BODY if k != "vehicle_id"})
    assert r.status_code == 200
    assert r.json() == {"saga_id": SAGA, "released": False}


def test_listar_y_registrar(client):
    assert client.get("/stations/st-1/connectors").json()[0]["connector_id"] == "c1"
    r = client.put("/stations/st-1/connectors/c1", json={"power_kw": 50, "status": "FAULTED"})
    assert r.json()["status"] == "FAULTED"
