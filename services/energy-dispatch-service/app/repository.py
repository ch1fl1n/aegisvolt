"""Sesiones de carga en DynamoDB: una por saga, idempotentes, con TTL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from .models import Session, SessionStatus, StartRequest

SESSION_SK = "SESSION"
RETENTION_DAYS = 30  # DynamoDB borra la sesión sola pasado este tiempo (TTL)


def _condition_failed(exc: ClientError) -> bool:
    return exc.response["Error"]["Code"] == "ConditionalCheckFailedException"


class DispatchRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    def get(self, saga_id: str) -> Session | None:
        resp = self._table.get_item(Key={"saga_id": saga_id, "sk": SESSION_SK}, ConsistentRead=True)
        item = resp.get("Item")
        return Session.model_validate(item) if item else None

    def start(self, req: StartRequest, *, fault: bool) -> Session:
        """Crea la sesión (ACTIVE o FAULTED). Si la saga ya tiene una, devuelve esa."""
        now = datetime.now(UTC)
        status = SessionStatus.FAULTED if fault else SessionStatus.ACTIVE
        item = {
            "saga_id": req.saga_id,
            "sk": SESSION_SK,
            "station_id": req.station_id,
            "connector_id": req.connector_id,
            "vehicle_id": req.vehicle_id,
            "power_kw": Decimal(str(req.power_kw)),
            "status": status.value,
            "started_at": now.isoformat(timespec="seconds"),
            # TTL de DynamoDB: entero con segundos epoch, no texto.
            "expires_at": int((now + timedelta(days=RETENTION_DAYS)).timestamp()),
        }
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(saga_id)")
        except ClientError as exc:
            if not _condition_failed(exc):
                raise
            existing = self.get(req.saga_id)
            if existing is None:  # no debería pasar: la condición falló porque existe
                raise
            return existing  # reintento: mismo resultado que la primera vez
        return Session.model_validate(item)

    def stop(self, saga_id: str) -> bool:
        """Compensación / fin de carga. True si detuvo; False si no había sesión ACTIVE."""
        try:
            self._table.update_item(
                Key={"saga_id": saga_id, "sk": SESSION_SK},
                UpdateExpression="SET #st = :stopped, ended_at = :now",
                ConditionExpression="#st = :active",
                ExpressionAttributeNames={"#st": "status"},  # palabra reservada
                ExpressionAttributeValues={
                    ":stopped": SessionStatus.STOPPED.value,
                    ":active": SessionStatus.ACTIVE.value,
                    ":now": datetime.now(UTC).isoformat(timespec="seconds"),
                },
            )
        except ClientError as exc:
            if _condition_failed(exc):
                return False
            raise
        return True
