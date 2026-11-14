"""Repositorio contra Floci real (tabla aegisvolt-reservations-dev creada por Terraform)."""

import uuid

import pytest

from aegis_common import aws
from aegis_common.errors import ChargerFaultError, ConflictError, NotFoundError
from app.config import ReservationSettings
from app.models import ConnectorIn, ConnectorStatus, ReleaseRequest, ReservationRequest
from app.repository import ReservationRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AEGIS_ENV", "dev")
    monkeypatch.setenv("SERVICE_NAME", "station-reservation-service")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    settings = ReservationSettings()  # type: ignore[call-arg]
    table = aws.resource("dynamodb", settings).Table(settings.table)
    try:
        table.load()
    except Exception:
        pytest.skip("Floci no responde o la tabla no existe (¿dev.py up + terraform apply?)")
    return ReservationRepository(table)


@pytest.fixture
def station() -> str:
    return f"st-{uuid.uuid4().hex[:8]}"  # estación única por test: no chocan entre sí


def _saga() -> str:
    return f"saga-{uuid.uuid4().hex[:12]}"


def _req(station: str, saga: str, connector: str = "c1") -> ReservationRequest:
    return ReservationRequest(
        saga_id=saga, station_id=station, connector_id=connector, vehicle_id="veh-001"
    )


def test_reserva_y_reintento_idempotente(repo, station):
    repo.put_connector(station, "c1", ConnectorIn(power_kw=150))
    saga = _saga()
    first = repo.reserve(_req(station, saga))
    again = repo.reserve(_req(station, saga))  # reintento de la MISMA saga
    assert first.status is ConnectorStatus.RESERVED
    assert again.saga_id == saga
    assert again.reserved_at == first.reserved_at


def test_otra_saga_recibe_conflicto(repo, station):
    repo.put_connector(station, "c1", ConnectorIn(power_kw=50))
    repo.reserve(_req(station, _saga()))
    with pytest.raises(ConflictError):
        repo.reserve(_req(station, _saga()))


def test_conector_averiado_es_error_de_negocio(repo, station):
    repo.put_connector(station, "c1", ConnectorIn(power_kw=50, status=ConnectorStatus.FAULTED))
    with pytest.raises(ChargerFaultError):
        repo.reserve(_req(station, _saga()))


def test_conector_inexistente(repo, station):
    with pytest.raises(NotFoundError):
        repo.reserve(_req(station, _saga(), connector="no-existe"))


def test_compensacion_libera_y_es_idempotente(repo, station):
    repo.put_connector(station, "c1", ConnectorIn(power_kw=22))
    saga = _saga()
    repo.reserve(_req(station, saga))
    rel = ReleaseRequest(saga_id=saga, station_id=station, connector_id="c1")
    assert repo.release(rel) is True
    assert repo.release(rel) is False  # segunda vez: no hace nada y no falla
    current = repo.get_connector(station, "c1")
    assert current.status is ConnectorStatus.AVAILABLE
    assert current.saga_id is None


def test_gsi_por_saga(repo, station):
    repo.put_connector(station, "c1", ConnectorIn(power_kw=22))
    saga = _saga()
    repo.reserve(_req(station, saga))
    found = repo.find_by_saga(saga)
    assert [c.connector_id for c in found] == ["c1"]
