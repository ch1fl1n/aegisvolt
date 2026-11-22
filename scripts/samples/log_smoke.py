"""Envía logs de prueba a CloudWatch (Floci) y los busca por correlation_id.

Uso (con Floci arriba y . .\\scripts\\env.ps1 cargado):
    uv run python scripts/samples/log_smoke.py
"""

import logging
import os
import time

os.environ.setdefault("SERVICE_NAME", "graphql-gateway")
os.environ.setdefault("CLOUDWATCH_LOGS_ENABLED", "true")

from aegis_common.aws import client  # noqa: E402
from aegis_common.config import get_settings  # noqa: E402
from aegis_common.context import correlation_id_var, new_id  # noqa: E402
from aegis_common.logs import configure_logging  # noqa: E402

settings = get_settings()
configure_logging(settings)
log = logging.getLogger("smoke")

cid = new_id()
correlation_id_var.set(cid)
log.info("prueba de logging estructurado", extra={"event": "smoke_test"})
log.error("error simulado", extra={"event": "http_request", "status": 503})
logging.shutdown()  # vacía la cola hacia CloudWatch

time.sleep(1)
found = client("logs", settings).filter_log_events(
    logGroupName=settings.log_group,
    filterPattern=f'{{ $.correlation_id = "{cid}" }}',
)["events"]
print(f"\ncorrelation_id = {cid}")
print(f"log group      = {settings.log_group}")
print(f"eventos encontrados en CloudWatch: {len(found)}")
