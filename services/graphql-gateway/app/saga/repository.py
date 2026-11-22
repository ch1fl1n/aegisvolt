"""Bitácora de sagas en DynamoDB (tabla aegisvolt-sagas-<env>)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import anyio
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .models import SagaRecord, SagaStatus

STATUS_INDEX = "by-status"


class SagaAlreadyExistsError(Exception):
    """Ya hay una saga con ese saga_id (reintento del cliente o carrera entre réplicas)."""


def _to_item(record: SagaRecord) -> dict[str, Any]:
    """Pydantic -> JSON -> dict con Decimal: DynamoDB no acepta float."""
    return json.loads(record.model_dump_json(), parse_float=Decimal)


class SagaRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    def _put_new(self, item: dict[str, Any]) -> None:
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(saga_id)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise SagaAlreadyExistsError(item["saga_id"]) from None
            raise

    async def create(self, record: SagaRecord) -> None:
        await anyio.to_thread.run_sync(self._put_new, _to_item(record))

    async def save(self, record: SagaRecord) -> None:
        item = _to_item(record)
        await anyio.to_thread.run_sync(lambda: self._table.put_item(Item=item))

    async def get(self, saga_id: str) -> SagaRecord | None:
        resp = await anyio.to_thread.run_sync(
            lambda: self._table.get_item(Key={"saga_id": saga_id}, ConsistentRead=True)
        )
        item = resp.get("Item")
        return SagaRecord.model_validate(item) if item else None

    async def list_by_status(self, status: SagaStatus, limit: int = 20) -> list[SagaRecord]:
        """Las más recientes primero (GSI by-status: status + updated_at)."""
        resp = await anyio.to_thread.run_sync(
            lambda: self._table.query(
                IndexName=STATUS_INDEX,
                KeyConditionExpression=Key("status").eq(status.value),
                ScanIndexForward=False,
                Limit=limit,
            )
        )
        return [SagaRecord.model_validate(i) for i in resp["Items"]]
