"""Orquestador con clientes, bitácora y flags falsos: los 3 escenarios de la rúbrica."""

from types import SimpleNamespace

import pytest

from app.clients import DownstreamError
from app.saga.models import SagaStatus, StartChargeInput
from app.saga.orchestrator import SagaOrchestrator

DATA = StartChargeInput(
    station_id="st-1", connector_id="c1", vehicle_id="veh-1", account_id="acc-1", energy_kwh=10
)
FLAG_NAMES = {
    "surge": "ENABLE_DYNAMIC_SURGE_PRICING",
    "boost": "ENABLE_FAST_CHARGE_BOOST",
    "fault": "SIMULATE_CHARGER_HARDWARE_FAULT",
}


class Recorder:
    """Registra cada llamada a los servicios y lanza el error que se le configure."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.args: dict[str, tuple] = {}
        self.fail: dict[str, DownstreamError] = {}

    def fn(self, name: str):
        async def call(*args):
            self.calls.append(name)
            self.args[name] = args
            if name in self.fail:
                raise self.fail[name]
            return {}

        return call

    def clients(self):
        return SimpleNamespace(
            reservations=SimpleNamespace(reserve=self.fn("reserve"), release=self.fn("release")),
            billing=SimpleNamespace(charge=self.fn("charge"), refund=self.fn("refund")),
            dispatch=SimpleNamespace(start=self.fn("start"), stop=self.fn("stop")),
        )


class FakeRepo:
    """Bitácora en memoria: guarda la secuencia de estados que se persistieron."""

    def __init__(self) -> None:
        self.records: dict = {}
        self.statuses: list[SagaStatus] = []

    async def get(self, saga_id):
        return self.records.get(saga_id)

    async def create(self, record):
        self.records[record.saga_id] = record
        self.statuses.append(record.status)

    async def save(self, record):
        self.records[record.saga_id] = record
        self.statuses.append(record.status)


class FakeFlags:
    def __init__(self, **on: bool) -> None:
        self.on = on

    async def all(self):
        return {FLAG_NAMES[k]: v for k, v in self.on.items()}


@pytest.fixture
def rec() -> Recorder:
    return Recorder()


def _orch(rec: Recorder, repo: FakeRepo | None = None, **flags: bool) -> SagaOrchestrator:
    return SagaOrchestrator(
        repo or FakeRepo(),  # type: ignore[arg-type]
        rec.clients(),  # type: ignore[arg-type]
        FakeFlags(**flags),  # type: ignore[arg-type]
        id_factory=lambda: "saga-test-1",
    )


def _err(status: int | None, code: str) -> DownstreamError:
    return DownstreamError("x", status, code, "msg")


async def test_camino_feliz(rec):
    repo = FakeRepo()
    saga = await _orch(rec, repo).start_charge(DATA)
    assert saga.status is SagaStatus.COMPLETED
    assert rec.calls == ["reserve", "charge", "start"]
    assert saga.amount_cents == 800  # 10 kWh x 80 centavos
    assert repo.statuses == ["STARTED", "RESERVED", "CHARGED", "COMPLETED"]


async def test_fondos_insuficientes_libera_el_conector(rec):
    rec.fail["charge"] = _err(402, "INSUFFICIENT_FUNDS")
    saga = await _orch(rec).start_charge(DATA)
    assert saga.status is SagaStatus.COMPENSATED
    assert saga.error_code == "INSUFFICIENT_FUNDS"
    assert rec.calls == ["reserve", "charge", "refund", "release"]
    assert "start" not in rec.calls


async def test_falla_de_cargador_reembolsa_y_luego_libera(rec):
    rec.fail["start"] = _err(422, "CHARGER_FAULT")
    saga = await _orch(rec).start_charge(DATA)
    assert saga.status is SagaStatus.COMPENSATED
    assert rec.calls == ["reserve", "charge", "start", "stop", "refund", "release"]
    assert [h.action for h in saga.history].count("compensate") == 3


async def test_compensacion_que_falla_deja_la_saga_failed(rec):
    rec.fail["charge"] = _err(402, "INSUFFICIENT_FUNDS")
    rec.fail["release"] = _err(None, "UNAVAILABLE")
    saga = await _orch(rec).start_charge(DATA)
    assert saga.status is SagaStatus.FAILED
    assert saga.history[-1].outcome == "error"


async def test_flags_cambian_precio_potencia_y_simulan_falla(rec):
    rec.fail["start"] = _err(422, "CHARGER_FAULT")
    saga = await _orch(rec, surge=True, boost=True, fault=True).start_charge(DATA)
    assert saga.amount_cents == 1_200  # 10 kWh x 80 x 1,5
    assert saga.power_kw == 150
    assert rec.args["start"][-1] is True  # fault_injection enviado a dispatch
    assert saga.flags["SIMULATE_CHARGER_HARDWARE_FAULT"] is True


async def test_mismo_saga_id_no_ejecuta_dos_veces(rec):
    repo = FakeRepo()
    data = DATA.model_copy(update={"saga_id": "saga-cliente-1"})
    first = await _orch(rec, repo).start_charge(data)
    again = await _orch(rec, repo).start_charge(data)  # el cliente reintenta la mutación
    assert again.saga_id == first.saga_id == "saga-cliente-1"
    assert rec.calls == ["reserve", "charge", "start"]  # una sola vez
