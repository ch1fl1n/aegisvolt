"""Logging estructurado JSON + envío asíncrono a CloudWatch Logs.

Contrato de cada línea de log (lo usan los metric filters y Prefect):
    timestamp, level, logger, message, service, version, env,
    correlation_id, saga_id, + campos extra (event, status, ...)
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import sys
import threading
from datetime import UTC, datetime
from typing import Any

from .aws import client as aws_client
from .config import Settings
from .context import correlation_id_var, saga_id_var

# Atributos internos de LogRecord: no se copian al JSON.
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._static = {
            "service": settings.service_name,
            "version": settings.service_version,
            "env": settings.env,
        }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **self._static,
            "correlation_id": correlation_id_var.get(),
            "saga_id": saga_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value  # campos de extra={...}
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class CloudWatchHandler(logging.Handler):
    """Encola los logs y un hilo en segundo plano los envía en lotes.

    Nunca bloquea ni rompe la petición: si la cola se llena o CloudWatch falla,
    el log se descarta (y sigue saliendo por stdout).
    """

    def __init__(
        self,
        cw_client: Any,
        log_group: str,
        log_stream: str,
        flush_interval: float = 2.0,
        max_batch: int = 500,
    ) -> None:
        super().__init__()
        self._client = cw_client
        self._group = log_group
        self._stream = log_stream
        self._flush_interval = flush_interval
        self._max_batch = max_batch
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._ensure_stream()
        self._thread = threading.Thread(target=self._run, name="cloudwatch-logs", daemon=True)
        self._thread.start()

    def _ensure_stream(self) -> None:
        try:
            self._client.create_log_stream(logGroupName=self._group, logStreamName=self._stream)
        except self._client.exceptions.ResourceAlreadyExistsException:
            pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = {"timestamp": int(record.created * 1000), "message": self.format(record)}
            self._queue.put_nowait(event)
        except queue.Full:
            pass  # nunca bloquear la petición por culpa del logging
        except Exception:
            self.handleError(record)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._flush_interval)
            self.flush()

    def flush(self) -> None:
        with self._send_lock:
            batch: list[dict[str, Any]] = []
            while len(batch) < self._max_batch:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if not batch:
                return
            batch.sort(key=lambda e: e["timestamp"])  # CloudWatch exige orden cronológico
            try:
                self._client.put_log_events(
                    logGroupName=self._group, logStreamName=self._stream, logEvents=batch
                )
            except Exception as exc:  # el error del envío va a stderr, no a la app
                sys.stderr.write(f"[cloudwatch-logs] no se pudo enviar el lote: {exc}\n")

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self.flush()
        super().close()


def configure_logging(settings: Settings, cw_client: Any | None = None) -> logging.Logger:
    """Configura el logger raíz: JSON a stdout y, si está activado, a CloudWatch."""
    # Primero se silencian las librerías de AWS: son muy verbosas y podrían generar
    # logs en bucle al crear el cliente de CloudWatch.
    for noisy in ("botocore", "boto3", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    formatter = JsonFormatter(settings)
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    root.addHandler(stdout)

    if settings.cloudwatch_logs:
        stream = f"{settings.service_version}/{socket.gethostname()}-{os.getpid()}"
        handler = CloudWatchHandler(
            cw_client or aws_client("logs", settings), settings.log_group, stream
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)

    return root
