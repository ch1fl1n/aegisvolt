"""Casos de uso del servicio: lo que el resto del sistema puede pedirle."""

from __future__ import annotations

import logging

from .models import (
    ChargeRequest,
    RefundRequest,
    RefundResult,
    Transaction,
    Wallet,
    WalletIn,
)
from .repository import BillingRepository

log = logging.getLogger("billing")


class BillingService:
    def __init__(self, repo: BillingRepository) -> None:
        self._repo = repo

    # ---------- billetera ----------
    def get_wallet(self, account_id: str) -> Wallet:
        return self._repo.get_wallet(account_id)

    def set_wallet(self, account_id: str, data: WalletIn) -> Wallet:
        wallet = self._repo.put_wallet(account_id, data)
        log.info(
            "Billetera fijada",
            extra={
                "event": "wallet_set",
                "account_id": account_id,
                "balance_cents": wallet.balance_cents,
            },
        )
        return wallet

    def find_by_saga(self, saga_id: str) -> list[Transaction]:
        return self._repo.find_by_saga(saga_id)

    # ---------- SAGA ----------
    def charge(self, req: ChargeRequest) -> Transaction:
        """Paso 2 de la SAGA. Los errores (402/409/404) los lanza el repositorio."""
        tx = self._repo.charge(req)
        log.info(
            "Cobro registrado",
            extra={
                "event": "saga_step",
                "step": "charge_wallet",
                "outcome": "ok",
                "account_id": req.account_id,
                "amount_cents": tx.amount_cents,
            },
        )
        return tx

    def refund(self, req: RefundRequest) -> RefundResult:
        """Compensación del paso 2. Idempotente: reembolsar dos veces no es error."""
        result = self._repo.refund(req)
        log.info(
            "Compensación: reembolso",
            extra={
                "event": "saga_step",
                "step": "refund_wallet",
                "outcome": "refunded" if result.refunded else "noop",
                "account_id": req.account_id,
                "amount_cents": result.amount_cents,
            },
        )
        return result
