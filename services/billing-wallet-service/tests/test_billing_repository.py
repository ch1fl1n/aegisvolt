"""Repositorio contra Floci real (tabla aegisvolt-billing-dev creada por Terraform)."""

import uuid

import pytest

from aegis_common import aws
from aegis_common.errors import ConflictError, InsufficientFundsError, NotFoundError
from app.config import BillingSettings
from app.models import ChargeRequest, RefundRequest, TxType, WalletIn
from app.repository import BillingRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AEGIS_ENV", "dev")
    monkeypatch.setenv("SERVICE_NAME", "billing-wallet-service")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    settings = BillingSettings()  # type: ignore[call-arg]
    table = aws.resource("dynamodb", settings).Table(settings.table)
    try:
        table.load()
    except Exception:
        pytest.skip("Floci no responde o la tabla no existe (¿dev.py up + terraform apply?)")
    return BillingRepository(table)


@pytest.fixture
def account(repo) -> str:
    acc = f"acc-{uuid.uuid4().hex[:8]}"  # cuenta única por test
    repo.put_wallet(acc, WalletIn(balance_cents=10_000))  # 100,00
    return acc


def _saga() -> str:
    return f"saga-{uuid.uuid4().hex[:12]}"


def test_cobro_descuenta_y_reintento_no_cobra_dos_veces(repo, account):
    saga = _saga()
    req = ChargeRequest(saga_id=saga, account_id=account, amount_cents=2_500)
    first = repo.charge(req)
    again = repo.charge(req)  # reintento de la MISMA saga
    assert again.created_at == first.created_at
    assert repo.get_wallet(account).balance_cents == 7_500


def test_fondos_insuficientes_no_toca_nada(repo, account):
    saga = _saga()
    with pytest.raises(InsufficientFundsError):
        repo.charge(ChargeRequest(saga_id=saga, account_id=account, amount_cents=50_000))
    assert repo.get_wallet(account).balance_cents == 10_000
    assert repo.get_tx(account, saga, TxType.CHARGE) is None  # la transacción no dejó rastro


def test_misma_saga_con_otro_monto_es_conflicto(repo, account):
    saga = _saga()
    repo.charge(ChargeRequest(saga_id=saga, account_id=account, amount_cents=1_000))
    with pytest.raises(ConflictError):
        repo.charge(ChargeRequest(saga_id=saga, account_id=account, amount_cents=9_000))


def test_reembolso_devuelve_lo_cobrado_una_sola_vez(repo, account):
    saga = _saga()
    repo.charge(ChargeRequest(saga_id=saga, account_id=account, amount_cents=3_000))
    first = repo.refund(RefundRequest(saga_id=saga, account_id=account))
    again = repo.refund(RefundRequest(saga_id=saga, account_id=account))
    assert (first.refunded, first.amount_cents) == (True, 3_000)
    assert (again.refunded, again.amount_cents) == (False, 3_000)
    assert repo.get_wallet(account).balance_cents == 10_000


def test_reembolso_sin_cobro_no_hace_nada(repo, account):
    result = repo.refund(RefundRequest(saga_id=_saga(), account_id=account))
    assert result.refunded is False
    assert repo.get_wallet(account).balance_cents == 10_000


def test_billetera_inexistente(repo):
    with pytest.raises(NotFoundError):
        repo.charge(ChargeRequest(saga_id=_saga(), account_id="acc-no-existe", amount_cents=100))


def test_gsi_por_saga(repo, account):
    saga = _saga()
    repo.charge(ChargeRequest(saga_id=saga, account_id=account, amount_cents=500))
    repo.refund(RefundRequest(saga_id=saga, account_id=account))
    types = {t.type for t in repo.find_by_saga(saga)}
    assert types == {TxType.CHARGE, TxType.REFUND}
