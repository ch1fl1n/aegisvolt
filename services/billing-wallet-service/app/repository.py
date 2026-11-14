"""Billeteras en DynamoDB: cobro y reembolso atómicos con TransactWriteItems."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from aegis_common.errors import ConflictError, InsufficientFundsError, NotFoundError

from .models import (
    ChargeRequest,
    RefundRequest,
    RefundResult,
    Transaction,
    TxType,
    Wallet,
    WalletIn,
)

WALLET_SK = "WALLET"
SAGA_INDEX = "by-saga"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _tx_sk(saga_id: str, tx_type: TxType) -> str:
    return f"TX#{saga_id}#{tx_type.value}"


def _canceled(exc: ClientError) -> bool:
    return exc.response["Error"]["Code"] == "TransactionCanceledException"


class BillingRepository:
    def __init__(self, table: Any) -> None:
        self._table = table
        self._name: str = table.name
        # TransactWriteItems vive en el cliente. El cliente del "resource" convierte
        # tipos de Python <-> DynamoDB solo, igual que Table.
        self._client = table.meta.client

    # ---------- billetera ----------
    def put_wallet(self, account_id: str, data: WalletIn) -> Wallet:
        item = {
            "account_id": account_id,
            "sk": WALLET_SK,
            "balance_cents": data.balance_cents,
            "updated_at": _now(),
        }
        self._table.put_item(Item=item)
        return Wallet.model_validate(item)

    def get_wallet(self, account_id: str) -> Wallet:
        resp = self._table.get_item(
            Key={"account_id": account_id, "sk": WALLET_SK}, ConsistentRead=True
        )
        item = resp.get("Item")
        if item is None:
            raise NotFoundError("Billetera no existe", details={"account_id": account_id})
        return Wallet.model_validate(item)

    # ---------- transacciones ----------
    def get_tx(self, account_id: str, saga_id: str, tx_type: TxType) -> Transaction | None:
        resp = self._table.get_item(
            Key={"account_id": account_id, "sk": _tx_sk(saga_id, tx_type)},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        return Transaction.model_validate(item) if item else None

    def find_by_saga(self, saga_id: str) -> list[Transaction]:
        resp = self._table.query(
            IndexName=SAGA_INDEX, KeyConditionExpression=Key("saga_id").eq(saga_id)
        )
        return [Transaction.model_validate(i) for i in resp["Items"]]

    # ---------- SAGA: cobro ----------
    def charge(self, req: ChargeRequest) -> Transaction:
        """Paso SAGA. Atómico: descuenta saldo + registra TX, o no hace ninguna de las dos."""
        existing = self.get_tx(req.account_id, req.saga_id, TxType.CHARGE)
        if existing:
            return self._same_amount(existing, req.amount_cents)  # reintento

        now = _now()
        tx_item = {
            "account_id": req.account_id,
            "sk": _tx_sk(req.saga_id, TxType.CHARGE),
            "saga_id": req.saga_id,
            "type": TxType.CHARGE.value,
            "amount_cents": req.amount_cents,
            "created_at": now,
        }
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self._name,
                            "Key": {"account_id": req.account_id, "sk": WALLET_SK},
                            "UpdateExpression": (
                                "SET balance_cents = balance_cents - :amt, updated_at = :now"
                            ),
                            "ConditionExpression": (
                                "attribute_exists(account_id) AND balance_cents >= :amt"
                            ),
                            "ExpressionAttributeValues": {":amt": req.amount_cents, ":now": now},
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._name,
                            "Item": tx_item,
                            "ConditionExpression": "attribute_not_exists(sk)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if not _canceled(exc):
                raise
            return self._after_failed_charge(req)
        return Transaction.model_validate(tx_item)

    def _after_failed_charge(self, req: ChargeRequest) -> Transaction:
        """La transacción se canceló: se lee el estado para dar la respuesta correcta."""
        existing = self.get_tx(req.account_id, req.saga_id, TxType.CHARGE)
        if existing:  # otra réplica cobró esta misma saga un instante antes
            return self._same_amount(existing, req.amount_cents)
        wallet = self.get_wallet(req.account_id)  # 404 si no existe
        if wallet.balance_cents < req.amount_cents:
            raise InsufficientFundsError(
                "Saldo insuficiente",
                details={"balance_cents": wallet.balance_cents, "amount_cents": req.amount_cents},
            )
        raise ConflictError("Cobro concurrente sobre la billetera; reintente")

    @staticmethod
    def _same_amount(existing: Transaction, amount_cents: int) -> Transaction:
        if existing.amount_cents != amount_cents:
            raise ConflictError(
                "La saga ya registró un cobro con otro monto",
                details={"amount_cents": existing.amount_cents},
            )
        return existing

    # ---------- SAGA: compensación ----------
    def refund(self, req: RefundRequest) -> RefundResult:
        """Compensación idempotente. Devuelve EXACTAMENTE lo cobrado, una sola vez."""
        charge = self.get_tx(req.account_id, req.saga_id, TxType.CHARGE)
        if charge is None:
            return RefundResult(saga_id=req.saga_id, refunded=False)  # nada que devolver
        if self.get_tx(req.account_id, req.saga_id, TxType.REFUND):
            return RefundResult(
                saga_id=req.saga_id, refunded=False, amount_cents=charge.amount_cents
            )

        now = _now()
        refund_item = {
            "account_id": req.account_id,
            "sk": _tx_sk(req.saga_id, TxType.REFUND),
            "saga_id": req.saga_id,
            "type": TxType.REFUND.value,
            "amount_cents": charge.amount_cents,
            "created_at": now,
        }
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._name,
                            "Item": refund_item,
                            "ConditionExpression": "attribute_not_exists(sk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._name,
                            "Key": {"account_id": req.account_id, "sk": WALLET_SK},
                            "UpdateExpression": (
                                "SET balance_cents = balance_cents + :amt, updated_at = :now"
                            ),
                            "ConditionExpression": "attribute_exists(account_id)",
                            "ExpressionAttributeValues": {
                                ":amt": charge.amount_cents,
                                ":now": now,
                            },
                        }
                    },
                ]
            )
        except ClientError as exc:
            if _canceled(exc) and self.get_tx(req.account_id, req.saga_id, TxType.REFUND):
                return RefundResult(
                    saga_id=req.saga_id, refunded=False, amount_cents=charge.amount_cents
                )
            raise
        return RefundResult(saga_id=req.saga_id, refunded=True, amount_cents=charge.amount_cents)
