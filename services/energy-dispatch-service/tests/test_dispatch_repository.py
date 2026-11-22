"""Repositorio contra Floci real (tabla aegisvolt-dispatch-dev creada por Terraform)."""

import time
import uuid

import pytest

from aegis_common import aws
from app.config import DispatchSettings
from app.models import SessionStatus, StartRequest
from app.repository import SESSION_SK, DispatchRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AEGIS_ENV", "dev")
    monkeypatch.setenv("SERVICE_NAME", "energy-dispatch-service")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    settings = DispatchSettings()  # type: ignore[call-arg]
    tbl = aws.resource("dynamodb", settings).Table(settings.table)
    try:
        tbl.load()
    except Exception:
        pytest.skip("Floci no responde o la tabla no existe (¿dev.py up + terraform apply?)")
    return tbl


@pytest.fixture
def repo(table) -> DispatchRepository:
    return DispatchRepository(table)


def _req(saga: str) -> StartRequest:
    return StartRequest(
        saga_id=saga, station_id="st-1", connector_id="c1", vehicle_id="veh-1", power_kw=50
    )


def _saga() -> str:
    return f"saga-{uuid.uuid4().hex[:12]}"


def test_inicio_y_reintento_idempotente(repo):
    saga = _saga()
    first = repo.start(_req(saga), fault=False)
    again = repo.start(_req(saga), fault=False)
    assert first.status is SessionStatus.ACTIVE
    assert again.started_at == first.started_at


def test_fallo_queda_registrado_y_se_repite_igual(repo):
    saga = _saga()
    first = repo.start(_req(saga), fault=True)
    again = repo.start(_req(saga), fault=False)  # reintento: NO "se arregla" solo
    assert first.status is SessionStatus.FAULTED
    assert again.status is SessionStatus.FAULTED


def test_stop_es_idempotente(repo):
    saga = _saga()
    repo.start(_req(saga), fault=False)
    assert repo.stop(saga) is True
    assert repo.stop(saga) is False
    session = repo.get(saga)
    assert session is not None
    assert session.status is SessionStatus.STOPPED
    assert session.ended_at is not None


def test_stop_sin_sesion_no_falla(repo):
    assert repo.stop(_saga()) is False


def test_ttl_es_epoch_futuro(repo, table):
    saga = _saga()
    repo.start(_req(saga), fault=False)
    item = table.get_item(Key={"saga_id": saga, "sk": SESSION_SK})["Item"]
    days = (int(item["expires_at"]) - time.time()) / 86_400
    assert 29 < days <= 30
