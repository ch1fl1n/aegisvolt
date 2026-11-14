"""Modelos del dominio y contratos de entrada/salida. Dinero SIEMPRE en centavos (int)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

ID_PATTERN = r"^[A-Za-z0-9-]{1,64}$"
SafeId = Annotated[str, Field(pattern=ID_PATTERN)]
Cents = Annotated[int, Field(gt=0, le=10_000_000)]  # máximo 100.000,00 por cobro


class TxType(StrEnum):
    CHARGE = "CHARGE"
    REFUND = "REFUND"


class Wallet(BaseModel):
    account_id: str
    balance_cents: int
    updated_at: str | None = None


class WalletIn(BaseModel):
    """Crear o fijar el saldo de una billetera (seed y demo)."""

    balance_cents: int = Field(ge=0, le=100_000_000)


class Transaction(BaseModel):
    account_id: str
    saga_id: str
    type: TxType
    amount_cents: int
    created_at: str


class ChargeRequest(BaseModel):
    saga_id: SafeId
    account_id: SafeId
    amount_cents: Cents


class RefundRequest(BaseModel):
    """Sin monto a propósito: se reembolsa lo que se cobró, no lo que pida el cliente."""

    saga_id: SafeId
    account_id: SafeId


class RefundResult(BaseModel):
    saga_id: str
    refunded: bool  # False = no había cobro o ya se reembolsó (idempotente)
    amount_cents: int = 0
