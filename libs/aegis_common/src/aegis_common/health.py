"""Sondas de salud para Kubernetes: liveness (/healthz) y readiness (/readyz)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

Check = Callable[[], None]  # lanza una excepción si la dependencia no está lista


def health_router(checks: dict[str, Check]) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/healthz")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/readyz")
    def readiness() -> JSONResponse:  # def (no async): los checks bloqueantes van al threadpool
        results: dict[str, str] = {}
        for name, check in checks.items():
            try:
                check()
                results[name] = "ok"
            except Exception as exc:  # solo el TIPO de error, nunca el mensaje interno
                results[name] = f"error: {type(exc).__name__}"
        ready = all(v == "ok" for v in results.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "degraded", "checks": results},
        )

    return router


def dynamodb_table_check(ddb_client: Any, table_name: str) -> Check:
    def _check() -> None:
        ddb_client.describe_table(TableName=table_name)

    return _check
