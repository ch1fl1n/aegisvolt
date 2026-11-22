"""Bitácora de sagas contra Floci real (tabla aegisvolt-sagas-dev)."""

import uuid

import pytest

from aegis_common import aws
from app.config import GatewaySettings
from app.saga.models import SagaRecord, SagaStatus
from app.saga.repository import SagaAlreadyExistsError, SagaRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> SagaRepository:
    monkeypatch.setenv("AEGIS_ENV", "dev")
    monkeypatch.setenv("SERVICE_NAME", "graphql-gateway")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    settings = GatewaySettings()  # type: ignore[call-arg]
    table = aws.resource("dynamodb", settings).Table(settings.sagas_table)
    try:
        table.load()
    except Exception:
        pytest.skip("Floci no responde o la tabla no existe (¿dev.py up + terraform apply?)")
    return SagaRepository(table)


def _record() -> SagaRecord:
    return SagaRecord(
        saga_id=f"saga-{uuid.uuid4().hex[:12]}",
        status=SagaStatus.STARTED,
        station_id="st-1",
        connector_id="c1",
        vehicle_id="veh-1",
        account_id="acc-1",
        energy_kwh=12.5,  # float: comprueba la conversión a Decimal
        amount_cents=1_000,
        power_kw=50.0,
        flags={"ENABLE_FAST_CHARGE_BOOST": False},
        created_at="2026-11-14T00:00:00.000+00:00",
        updated_at="2026-11-14T00:00:00.000+00:00",
    )


async def test_crear_guardar_y_leer(repo):
    record = _record()
    await repo.create(record)
    record.status = SagaStatus.COMPENSATED
    record.updated_at = "2026-11-14T00:00:01.000+00:00"
    await repo.save(record)
    loaded = await repo.get(record.saga_id)
    assert loaded is not None
    assert loaded.status is SagaStatus.COMPENSATED
    assert loaded.energy_kwh == 12.5


async def test_no_se_crea_dos_veces(repo):
    record = _record()
    await repo.create(record)
    with pytest.raises(SagaAlreadyExistsError):
        await repo.create(record)


async def test_listar_por_estado(repo):
    record = _record()
    record.status = SagaStatus.FAILED
    await repo.create(record)
    failed = await repo.list_by_status(SagaStatus.FAILED, limit=50)
    assert record.saga_id in {s.saga_id for s in failed}
