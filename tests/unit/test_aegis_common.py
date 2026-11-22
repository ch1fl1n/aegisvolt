"""Pruebas de la librería común (no necesitan Floci)."""

import json
import logging

import pytest

from aegis_common.config import Settings, get_settings
from aegis_common.context import correlation_id_var, sanitize_id
from aegis_common.logs import CloudWatchHandler, JsonFormatter


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("AEGIS_ENV", "test")
    monkeypatch.setenv("SERVICE_NAME", "billing-wallet-service")
    monkeypatch.setenv("SERVICE_VERSION", "v2")
    get_settings.cache_clear()
    return get_settings()


def test_nombres_por_ambiente(settings: Settings) -> None:
    assert settings.table_name("billing") == "aegisvolt-billing-test"
    assert settings.log_group == "/aegisvolt/test/billing-wallet-service"


def test_ambiente_invalido_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGIS_ENV", "produccion")
    monkeypatch.setenv("SERVICE_NAME", "x")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


@pytest.mark.parametrize(
    "valor",
    [None, "", "corto", 'abc"}\n{"level":"FAKE', "a" * 100, "id con espacios"],
)
def test_ids_inseguros_se_reemplazan(valor: str | None) -> None:
    resultado = sanitize_id(valor)
    assert resultado != valor
    assert len(resultado) == 36  # uuid4


def test_id_seguro_se_conserva() -> None:
    assert sanitize_id("8f2c1a3e-1111-2222-3333-444455556666") == (
        "8f2c1a3e-1111-2222-3333-444455556666"
    )


def test_formato_json_cumple_el_contrato(settings: Settings) -> None:
    correlation_id_var.set("corr-12345678")
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "fallo", (), None)
    record.event = "http_request"
    record.status = 503

    data = json.loads(JsonFormatter(settings).format(record))

    assert data["service"] == "billing-wallet-service"
    assert data["version"] == "v2"
    assert data["env"] == "test"
    assert data["correlation_id"] == "corr-12345678"
    assert data["event"] == "http_request"
    assert data["status"] == 503


class FakeLogsClient:
    """Imita al cliente de CloudWatch Logs para no depender de Floci."""

    class exceptions:  # noqa: N801 (imita la API de boto3)
        class ResourceAlreadyExistsException(Exception):
            pass

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def create_log_stream(self, **_: str) -> None:
        return None

    def put_log_events(self, **kwargs: object) -> None:
        self.sent.append(kwargs)


def test_cloudwatch_handler_envia_en_orden(settings: Settings) -> None:
    fake = FakeLogsClient()
    handler = CloudWatchHandler(fake, "/g", "s", flush_interval=60)
    handler.setFormatter(JsonFormatter(settings))
    logger = logging.getLogger("cw-test")
    logger.addHandler(handler)
    logger.propagate = False

    logger.warning("uno")
    logger.warning("dos")
    handler.close()  # fuerza el envío

    eventos = fake.sent[0]["logEvents"]
    assert [json.loads(e["message"])["message"] for e in eventos] == ["uno", "dos"]
    assert eventos[0]["timestamp"] <= eventos[1]["timestamp"]
