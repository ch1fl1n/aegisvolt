"""Endpoints HTTP. Los consume el orquestador SAGA del graphql-gateway."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from .models import (
    ID_PATTERN,
    Connector,
    ConnectorIn,
    ReleaseRequest,
    ReleaseResult,
    ReservationRequest,
)
from .service import ReservationService

PathId = Annotated[str, Path(pattern=ID_PATTERN)]


def get_service(request: Request) -> ReservationService:
    return request.app.state.service


Svc = Annotated[ReservationService, Depends(get_service)]

router = APIRouter(tags=["reservations"])


@router.get("/stations/{station_id}/connectors")
def list_connectors(station_id: PathId, svc: Svc) -> list[Connector]:
    return svc.list_connectors(station_id)


@router.put("/stations/{station_id}/connectors/{connector_id}")
def register_connector(
    station_id: PathId, connector_id: PathId, body: ConnectorIn, svc: Svc
) -> Connector:
    return svc.register_connector(station_id, connector_id, body)


@router.post("/reservations")
def reserve(body: ReservationRequest, svc: Svc) -> Connector:
    """Paso SAGA. 200 también en reintentos de la misma saga (idempotente)."""
    return svc.reserve(body)


@router.post("/reservations/release")
def release(body: ReleaseRequest, svc: Svc) -> ReleaseResult:
    """Compensación SAGA. Siempre 200: released=false si ya estaba libre."""
    return svc.release(body)


@router.get("/reservations/{saga_id}")
def by_saga(saga_id: PathId, svc: Svc) -> list[Connector]:
    return svc.find_by_saga(saga_id)
