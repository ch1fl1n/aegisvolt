"""Deja los dos flujos programados para los tres ambientes (un proceso, sin worker aparte).

    .venv/Scripts/python -m prefect server start          # terminal 1: UI en :4200
    .venv/Scripts/python serve.py   # terminal 2

Salud cada 5 minutos y auditoría cada 15, por ambiente. Ctrl+C detiene la programación.
"""

from __future__ import annotations

from health_flow import environment_health
from prefect import serve
from saga_audit_flow import saga_audit

if __name__ == "__main__":
    deployments = []
    for env in ("dev", "test", "prod"):
        deployments.append(
            environment_health.to_deployment(
                name=f"health-{env}", cron="*/5 * * * *", parameters={"env": env}, tags=[env]
            )
        )
        deployments.append(
            saga_audit.to_deployment(
                name=f"saga-audit-{env}", cron="*/15 * * * *", parameters={"env": env}, tags=[env]
            )
        )
    serve(*deployments)
