"""Los 3 escenarios de la rúbrica por GraphQL, con los 4 servicios reales contra Floci.

Además del resultado de la saga, se comprueba el ESTADO REAL en los otros servicios:
saldo de la billetera y estado del conector (que viven en sus propias tablas).
"""

import json
import os
import threading
import uuid
from types import SimpleNamespace

import pytest
from websockets.sync.client import connect

pytestmark = pytest.mark.e2e

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8000")
RESERVATIONS = "http://localhost:8001"
BILLING = "http://localhost:8002"
FLAGS = (
    "ENABLE_DYNAMIC_SURGE_PRICING",
    "ENABLE_FAST_CHARGE_BOOST",
    "SIMULATE_CHARGER_HARDWARE_FAULT",
)
START = """
mutation($input: StartChargeInput!) {
  startCharge(input: $input) {
    sagaId status amountCents powerKw errorCode
    history { step action outcome }
  }
}"""


def gql(http, query: str, variables=None, token: str | None = None) -> dict:
    headers = {"x-admin-token": token} if token else {}
    r = http.post(
        f"{GATEWAY}/graphql", json={"query": query, "variables": variables}, headers=headers
    )
    r.raise_for_status()
    body = r.json()
    assert "errors" not in body, body
    return body["data"]


def set_flag(http, token: str, name: str, enabled: bool) -> None:
    query = f"mutation {{ setFlag(name: {name}, enabled: {str(enabled).lower()}) {{ enabled }} }}"
    gql(http, query, token=token)


@pytest.fixture
def sc(http, admin_token):
    """Estación y cuenta nuevas por prueba; todas las flags apagadas antes y después."""
    tag = uuid.uuid4().hex[:8]
    data = SimpleNamespace(station=f"st-e2e-{tag}", account=f"acc-e2e-{tag}")
    url = f"{RESERVATIONS}/stations/{data.station}/connectors/c1"
    http.put(url, json={"power_kw": 150}).raise_for_status()
    for name in FLAGS:
        set_flag(http, admin_token, name, False)
    yield data
    for name in FLAGS:
        set_flag(http, admin_token, name, False)


def fund(http, account: str, cents: int) -> None:
    http.put(f"{BILLING}/wallets/{account}", json={"balance_cents": cents}).raise_for_status()


def start(http, sc, energy: float = 10, saga_id: str | None = None) -> dict:
    payload = {
        "stationId": sc.station,
        "connectorId": "c1",
        "vehicleId": "veh-e2e",
        "accountId": sc.account,
        "energyKwh": energy,
    }
    if saga_id:
        payload["sagaId"] = saga_id
    return gql(http, START, {"input": payload})["startCharge"]


def balance(http, account: str) -> int:
    query = f'{{ wallet(accountId: "{account}") {{ balanceCents }} }}'
    return gql(http, query)["wallet"]["balanceCents"]


def connector_status(http, station: str) -> str:
    query = f'{{ connectors(stationId: "{station}") {{ status }} }}'
    return gql(http, query)["connectors"][0]["status"]


def compensations(saga: dict) -> list[str]:
    return [h["step"] for h in saga["history"] if h["action"] == "compensate"]


def test_escenario_1_camino_feliz(http, sc):
    fund(http, sc.account, 10_000)
    saga = start(http, sc)
    assert saga["status"] == "COMPLETED"
    assert saga["amountCents"] == 800
    assert balance(http, sc.account) == 9_200  # se cobró UNA vez
    assert connector_status(http, sc.station) == "RESERVED"


def test_escenario_2_fondos_insuficientes_libera_el_conector(http, sc):
    fund(http, sc.account, 100)
    saga = start(http, sc)
    assert saga["status"] == "COMPENSATED"
    assert saga["errorCode"] == "INSUFFICIENT_FUNDS"
    assert compensations(saga) == ["charge_wallet", "reserve_connector"]
    assert balance(http, sc.account) == 100  # nada cobrado
    assert connector_status(http, sc.station) == "AVAILABLE"  # conector liberado


def test_escenario_3_falla_de_cargador_reembolsa_y_libera(http, sc, admin_token):
    fund(http, sc.account, 10_000)
    set_flag(http, admin_token, "SIMULATE_CHARGER_HARDWARE_FAULT", True)
    saga = start(http, sc)
    assert saga["status"] == "COMPENSATED"
    assert saga["errorCode"] == "CHARGER_FAULT"
    assert compensations(saga) == ["start_charging", "charge_wallet", "reserve_connector"]
    assert balance(http, sc.account) == 10_000  # se cobró y se reembolsó
    assert connector_status(http, sc.station) == "AVAILABLE"


def test_flags_cambian_precio_y_potencia_sin_redesplegar(http, sc, admin_token):
    fund(http, sc.account, 10_000)
    set_flag(http, admin_token, "ENABLE_DYNAMIC_SURGE_PRICING", True)
    set_flag(http, admin_token, "ENABLE_FAST_CHARGE_BOOST", True)
    saga = start(http, sc)
    assert saga["status"] == "COMPLETED"
    assert (saga["amountCents"], saga["powerKw"]) == (1_200, 150)
    assert balance(http, sc.account) == 8_800


def test_mismo_saga_id_no_cobra_dos_veces(http, sc):
    fund(http, sc.account, 10_000)
    saga_id = f"saga-e2e-{uuid.uuid4().hex[:8]}"
    first = start(http, sc, saga_id=saga_id)
    again = start(http, sc, saga_id=saga_id)  # el frontend reintenta la mutación
    assert first["sagaId"] == again["sagaId"] == saga_id
    assert balance(http, sc.account) == 9_200


def test_suscripcion_wss_ve_la_saga_en_tiempo_real(http, sc):
    fund(http, sc.account, 10_000)
    saga_id = f"saga-e2e-{uuid.uuid4().hex[:8]}"
    ws_url = GATEWAY.replace("http", "ws", 1) + "/graphql"
    sub = f'subscription {{ sagaUpdates(sagaId: "{saga_id}") {{ status }} }}'
    with connect(ws_url, subprotocols=["graphql-transport-ws"], open_timeout=10) as ws:
        ws.send(json.dumps({"type": "connection_init"}))
        assert json.loads(ws.recv(timeout=10))["type"] == "connection_ack"
        ws.send(json.dumps({"id": "1", "type": "subscribe", "payload": {"query": sub}}))
        # La suscripción se abre ANTES de la saga; la mutación corre en otro hilo.
        worker = threading.Thread(target=start, args=(http, sc), kwargs={"saga_id": saga_id})
        worker.start()
        statuses = []
        while (msg := json.loads(ws.recv(timeout=20)))["type"] == "next":
            statuses.append(msg["payload"]["data"]["sagaUpdates"]["status"])
        worker.join(timeout=20)
    assert msg["type"] == "complete"
    assert statuses[-1] == "COMPLETED"
