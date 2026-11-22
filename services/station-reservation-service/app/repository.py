"""Acceso a DynamoDB con escrituras condicionales (sin doble reserva, idempotente)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from aegis_common.errors import AegisError, ChargerFaultError, ConflictError, NotFoundError

from .models import Connector, ConnectorIn, ConnectorStatus, ReleaseRequest, ReservationRequest

SAGA_INDEX = "by-saga"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _condition_failed(exc: ClientError) -> bool:
    return exc.response["Error"]["Code"] == "ConditionalCheckFailedException"


class ReservationRepository:
    def __init__(self, table: Any) -> None:
        self._table = table  # boto3 Table (resource): convierte tipos de DynamoDB solo

    # ---------- inventario ----------
    def put_connector(self, station_id: str, connector_id: str, data: ConnectorIn) -> Connector:
        """Alta/actualización. No pisa un conector que tenga una reserva activa."""
        item = {
            "station_id": station_id,
            "connector_id": connector_id,
            "power_kw": Decimal(str(data.power_kw)),  # DynamoDB no acepta float
            "status": data.status.value,
        }
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(saga_id)")
        except ClientError as exc:
            if _condition_failed(exc):
                raise ConflictError("El conector tiene una reserva activa") from None
            raise
        return Connector.model_validate(item)

    def get_connector(self, station_id: str, connector_id: str) -> Connector:
        resp = self._table.get_item(
            Key={"station_id": station_id, "connector_id": connector_id}, ConsistentRead=True
        )
        item = resp.get("Item")
        if item is None:
            raise NotFoundError(
                "Conector no existe",
                details={"station_id": station_id, "connector_id": connector_id},
            )
        return Connector.model_validate(item)

    def list_connectors(self, station_id: str) -> list[Connector]:
        resp = self._table.query(
            KeyConditionExpression=Key("station_id").eq(station_id), ConsistentRead=True
        )
        return [Connector.model_validate(i) for i in resp["Items"]]

    def find_by_saga(self, saga_id: str) -> list[Connector]:
        """Lectura por GSI disperso (eventualmente consistente): para consultas, no para decidir."""
        resp = self._table.query(
            IndexName=SAGA_INDEX, KeyConditionExpression=Key("saga_id").eq(saga_id)
        )
        return [Connector.model_validate(i) for i in resp["Items"]]

    # ---------- SAGA ----------
    def reserve(self, req: ReservationRequest) -> Connector:
        """Paso de la SAGA. Atómico: solo si está AVAILABLE o ya es de ESTA saga (reintento)."""
        try:
            resp = self._table.update_item(
                Key={"station_id": req.station_id, "connector_id": req.connector_id},
                UpdateExpression=(
                    "SET #st = :reserved, saga_id = :saga, vehicle_id = :vehicle, "
                    "reserved_at = if_not_exists(reserved_at, :now)"
                ),
                ConditionExpression=(
                    "attribute_exists(station_id) AND (#st = :available OR saga_id = :saga)"
                ),
                ExpressionAttributeNames={"#st": "status"},  # "status" es palabra reservada
                ExpressionAttributeValues={
                    ":reserved": ConnectorStatus.RESERVED.value,
                    ":available": ConnectorStatus.AVAILABLE.value,
                    ":saga": req.saga_id,
                    ":vehicle": req.vehicle_id,
                    ":now": _now(),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if not _condition_failed(exc):
                raise
            raise self._why_not_reservable(req) from None
        return Connector.model_validate(resp["Attributes"])

    def release(self, req: ReleaseRequest) -> bool:
        """Compensación idempotente. True si liberó; False si ya no era de esta saga."""
        try:
            self._table.update_item(
                Key={"station_id": req.station_id, "connector_id": req.connector_id},
                UpdateExpression="SET #st = :available REMOVE saga_id, vehicle_id, reserved_at",
                ConditionExpression="saga_id = :saga AND #st = :reserved",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":available": ConnectorStatus.AVAILABLE.value,
                    ":reserved": ConnectorStatus.RESERVED.value,
                    ":saga": req.saga_id,
                },
            )
        except ClientError as exc:
            if _condition_failed(exc):
                return False
            raise
        return True

    def _why_not_reservable(self, req: ReservationRequest) -> AegisError:
        """La condición falló: se lee el estado para responder el error correcto."""
        current = self.get_connector(req.station_id, req.connector_id)  # 404 si no existe
        if current.status is ConnectorStatus.FAULTED:
            return ChargerFaultError("El conector está averiado", details={"status": "FAULTED"})
        # No se revela qué saga lo tiene: solo su estado.
        return ConflictError("El conector no está disponible", details={"status": current.status})
