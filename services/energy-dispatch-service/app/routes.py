"""Endpoints HTTP. Los consume el orquestador SAGA del graphql-gateway."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from .models import ID_PATTERN, Session, StartRequest, StopResult
from .service import DispatchService

PathId = Annotated[str, Path(pattern=ID_PATTERN)]


def get_service(request: Request) -> DispatchService:
    return request.app.state.service


Svc = Annotated[DispatchService, Depends(get_service)]

router = APIRouter(tags=["dispatch"])


@router.post("/sessions")
def start(body: StartRequest, svc: Svc) -> Session:
    """Paso SAGA. 422 CHARGER_FAULT si el cargador falla; 403 si se simula en prod."""
    return svc.start(body)


@router.post("/sessions/{saga_id}/stop")
def stop(saga_id: PathId, svc: Svc) -> StopResult:
    """Compensación SAGA. Siempre 200: stopped=false si no había sesión activa."""
    return svc.stop(saga_id)


@router.get("/sessions/{saga_id}")
def get_session(saga_id: PathId, svc: Svc) -> Session:
    return svc.get(saga_id)
