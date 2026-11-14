"""API GraphQL de punta a punta por HTTP y WebSocket, con dependencias falsas (sin Floci)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from aegis_common.config import get_settings as common_settings
from app.clients import DownstreamError
from app.config import GatewaySettings, get_settings
from app.flags import FlagStore
from app.main import build
from app.resolvers import Deps
from app.saga.models import SagaRecord, SagaStatus

TOKEN = "token-de-prueba"  # noqa: S105 (valor de prueba, no es un secreto real)
START = """
mutation($input: StartChargeInput!) {
  startCharge(input: $input) { sagaId status amountCents powerKw errorCode history { step } }
}"""
INPUT = {
    "stationId": "st-1",
    "connectorId": "c1",
    "vehicleId": "veh-1",
    "accountId": "acc-1",
    "energyKwh": 10,
}


def _record(status: SagaStatus, updated_at: str = "t1") -> SagaRecord:
    return SagaRecord(
        saga_id="saga-1",
        status=status,
        station_id="st-1",
        connector_id="c1",
        vehicle_id="veh-1",
        account_id="acc-1",
        energy_kwh=10,
        amount_cents=800,
        power_kw=50,
        flags={"ENABLE_FAST_CHARGE_BOOST": False},
        created_at="t0",
        updated_at=updated_at,
    )


class FakeOrchestrator:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.timeline: list[SagaRecord] = []  # lo que va viendo la suscripción

    async def start_charge(self, data):
        if self.error:
            raise self.error
        return _record(SagaStatus.COMPLETED)

    async def get(self, saga_id):
        if len(self.timeline) > 1:
            return self.timeline.pop(0)
        return self.timeline[0] if self.timeline else None

    async def list_by_status(self, status, limit):
        return [_record(status)]


class FakeTable:
    def __init__(self) -> None:
        self.items: dict = {}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}

    def put_item(self, Item):
        self.items[Item["flag_name"]] = Item


async def _not_found(account_id):
    raise DownstreamError("billing", 404, "NOT_FOUND", "Billetera no existe")


async def _noop():
    return None


def _app(monkeypatch: pytest.MonkeyPatch, env: str, orch: FakeOrchestrator):
    monkeypatch.setenv("AEGIS_ENV", env)
    monkeypatch.setenv("SERVICE_NAME", "graphql-gateway")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.delenv("CLOUDWATCH_LOGS_ENABLED", raising=False)
    get_settings.cache_clear()
    common_settings.cache_clear()
    settings = GatewaySettings()  # type: ignore[call-arg]
    clients = SimpleNamespace(
        billing=SimpleNamespace(get_wallet=_not_found),
        aclose=_noop,
    )
    deps = Deps(
        settings=settings,
        clients=clients,  # type: ignore[arg-type]
        flags=FlagStore(FakeTable(), ttl_s=0),
        orchestrator=orch,  # type: ignore[arg-type]
        poll_interval_s=0.01,
    )
    return build(settings, deps=deps)


@pytest.fixture
def orch() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture
def client(monkeypatch, orch) -> TestClient:
    return TestClient(_app(monkeypatch, "test", orch))


def _gql(client: TestClient, query: str, variables=None, headers=None) -> dict:
    r = client.post("/graphql", json={"query": query, "variables": variables}, headers=headers)
    assert r.status_code == 200
    return r.json()


def _code(body: dict) -> str:
    return body["errors"][0]["extensions"]["code"]


def test_start_charge(client):
    body = _gql(client, START, {"input": INPUT})
    saga = body["data"]["startCharge"]
    assert saga["status"] == "COMPLETED"
    assert saga["amountCents"] == 800


def test_validacion_de_entrada(client):
    body = _gql(client, START, {"input": {**INPUT, "energyKwh": 0}})
    assert _code(body) == "VALIDATION_ERROR"


def test_error_interno_se_enmascara(client, orch):
    orch.error = RuntimeError("detalle-secreto-de-boto3")
    body = _gql(client, START, {"input": INPUT})
    assert "detalle-secreto" not in str(body)
    assert body["errors"][0]["message"].startswith("Error interno")


def test_error_de_negocio_de_un_servicio_llega_con_su_codigo(client):
    body = _gql(client, '{ wallet(accountId: "acc-x") { balanceCents } }')
    assert _code(body) == "NOT_FOUND"


def test_flags_requieren_token_admin(client):
    mutation = "mutation { setFlag(name: ENABLE_FAST_CHARGE_BOOST, enabled: true) { enabled } }"
    assert _code(_gql(client, mutation)) == "FORBIDDEN"
    assert _code(_gql(client, mutation, headers={"x-admin-token": "otro"})) == "FORBIDDEN"
    ok = _gql(client, mutation, headers={"x-admin-token": TOKEN})
    assert ok["data"]["setFlag"]["enabled"] is True
    flags = _gql(client, "{ flags { name enabled } }")["data"]["flags"]
    assert {"name": "ENABLE_FAST_CHARGE_BOOST", "enabled": True} in flags


def test_consulta_demasiado_profunda_se_rechaza(client):
    deep = '{ saga(sagaId: "s-1") { history { step } ' + "flags { name } " * 1 + "} }"
    assert "errors" not in _gql(client, deep)
    nested = (
        '{ __type(name: "Saga") { fields { type { fields { type { fields { type '
        "{ fields { name } } } } } } } } }"
    )
    assert "depth" in _gql(client, nested)["errors"][0]["message"]


def test_introspeccion_apagada_en_prod(monkeypatch, orch):
    query = "{ __schema { queryType { name } } }"
    dev = TestClient(_app(monkeypatch, "dev", orch))
    assert "errors" not in _gql(dev, query)
    prod = TestClient(_app(monkeypatch, "prod", orch))
    assert "errors" in _gql(prod, query)


def test_suscripcion_saga_updates_por_websocket(client, orch):
    orch.timeline = [
        _record(SagaStatus.STARTED, "t1"),
        _record(SagaStatus.CHARGED, "t2"),
        _record(SagaStatus.COMPLETED, "t3"),
    ]
    sub = 'subscription { sagaUpdates(sagaId: "saga-1") { status } }'
    with client.websocket_connect("/graphql", subprotocols=["graphql-transport-ws"]) as ws:
        ws.send_json({"type": "connection_init"})
        assert ws.receive_json()["type"] == "connection_ack"
        ws.send_json({"id": "1", "type": "subscribe", "payload": {"query": sub}})
        statuses = []
        while (msg := ws.receive_json())["type"] == "next":
            statuses.append(msg["payload"]["data"]["sagaUpdates"]["status"])
        assert msg["type"] == "complete"  # la saga llegó a un estado final: se cierra sola
    assert statuses == ["STARTED", "CHARGED", "COMPLETED"]
