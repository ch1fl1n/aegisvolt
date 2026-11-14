"""Endpoints HTTP. Los consume el orquestador SAGA del graphql-gateway."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from .models import (
    ID_PATTERN,
    ChargeRequest,
    RefundRequest,
    RefundResult,
    Transaction,
    Wallet,
    WalletIn,
)
from .service import BillingService

PathId = Annotated[str, Path(pattern=ID_PATTERN)]


def get_service(request: Request) -> BillingService:
    return request.app.state.service


Svc = Annotated[BillingService, Depends(get_service)]

router = APIRouter(tags=["billing"])


@router.get("/wallets/{account_id}")
def get_wallet(account_id: PathId, svc: Svc) -> Wallet:
    return svc.get_wallet(account_id)


@router.put("/wallets/{account_id}")
def set_wallet(account_id: PathId, body: WalletIn, svc: Svc) -> Wallet:
    return svc.set_wallet(account_id, body)


@router.post("/charges")
def charge(body: ChargeRequest, svc: Svc) -> Transaction:
    """Paso SAGA. 200 también en reintentos de la misma saga y mismo monto."""
    return svc.charge(body)


@router.post("/charges/refund")
def refund(body: RefundRequest, svc: Svc) -> RefundResult:
    """Compensación SAGA. Siempre 200: refunded=false si no había nada que devolver."""
    return svc.refund(body)


@router.get("/transactions/{saga_id}")
def by_saga(saga_id: PathId, svc: Svc) -> list[Transaction]:
    return svc.find_by_saga(saga_id)
