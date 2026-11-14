"""API HTTP con un repositorio falso: valida rutas, códigos y formato de error (sin Floci)."""

import pytest
from fastapi.testclient import TestClient

from aegis_common.config import get_settings as common_settings
from aegis_common.errors import AegisError, ConflictError, InsufficientFundsError
from app.config import BillingSettings, get_settings
from app.main import build
from app.models import RefundResult, Transaction, TxType, Wallet
from app.service import BillingService

SAGA = "saga-0001"
CHARGE = {"saga_id": SAGA, "account_id": "acc-1", "amount_cents": 2_500}


class StubRepo:
    """Imita al repositorio: devuelve datos fijos o lanza el error que se le indique."""

    def __init__(self) -> None:
        self.error: AegisError | None = None
        self.refunded = True

    def charge(self, req):
        if self.error:
            raise self.error
        return Transaction(
            account_id=req.account_id,
            saga_id=req.saga_id,
            type=TxType.CHARGE,
            amount_cents=req.amount_cents,
            created_at="2026-11-14T00:00:00+00:00",
        )

    def refund(self, req):
        return RefundResult(saga_id=req.saga_id, refunded=self.refunded, amount_cents=2_500)

    def get_wallet(self, account_id):
        return Wallet(account_id=account_id, balance_cents=10_000)

    def put_wallet(self, account_id, data):
        return Wallet(account_id=account_id, balance_cents=data.balance_cents)

    def find_by_saga(self, saga_id):
        return []


@pytest.fixture
def repo() -> StubRepo:
    return StubRepo()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, repo: StubRepo) -> TestClient:
    monkeypatch.setenv("AEGIS_ENV", "test")
    monkeypatch.setenv("SERVICE_NAME", "billing-wallet-service")
    monkeypatch.delenv("CLOUDWATCH_LOGS_ENABLED", raising=False)
    get_settings.cache_clear()
    common_settings.cache_clear()
    settings = BillingSettings()  # type: ignore[call-arg]
    app = build(settings, service=BillingService(repo))  # type: ignore[arg-type]
    return TestClient(app)


def test_cobro_ok(client):
    r = client.post("/charges", json=CHARGE)
    assert r.status_code == 200
    assert r.json()["type"] == "CHARGE"
    assert r.json()["amount_cents"] == 2_500


def test_fondos_insuficientes_es_402(client, repo):
    repo.error = InsufficientFundsError("Saldo insuficiente")
    r = client.post("/charges", json=CHARGE)
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"


def test_otro_monto_misma_saga_es_409(client, repo):
    repo.error = ConflictError("La saga ya registró un cobro con otro monto")
    r = client.post("/charges", json=CHARGE)
    assert r.status_code == 409


def test_monto_invalido_es_rechazado(client):
    for bad in (0, -100, 2.5):  # cero, negativo y decimales: no son centavos válidos
        r = client.post("/charges", json={**CHARGE, "amount_cents": bad})
        assert r.status_code == 422, bad


def test_reembolso_idempotente(client, repo):
    repo.refunded = False  # ya se había reembolsado
    r = client.post("/charges/refund", json={"saga_id": SAGA, "account_id": "acc-1"})
    assert r.status_code == 200
    assert r.json() == {"saga_id": SAGA, "refunded": False, "amount_cents": 2_500}


def test_billetera(client):
    assert client.get("/wallets/acc-1").json()["balance_cents"] == 10_000
    r = client.put("/wallets/acc-1", json={"balance_cents": 5_000})
    assert r.json()["balance_cents"] == 5_000
