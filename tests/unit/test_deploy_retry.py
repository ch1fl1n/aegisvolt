"""Política de reintentos de deploy.py: solo transitorios, con tope, y registrados."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))  # deploy.py y canary.py importan retry.py

import retry as deploy  # noqa: E402  (la política vive en retry.py, compartida)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(deploy.time, "sleep", lambda _s: None)
    deploy.RETRY_LOG.clear()


def fake(results):
    calls = []

    def execute(cmd, stdin, env):
        calls.append(cmd)
        return results[min(len(calls), len(results)) - 1]

    return execute, calls


def test_error_permanente_no_se_reintenta(monkeypatch):
    execute, calls = fake([(1, "", "error: error parsing STDIN: yaml: line 3: bad indent")])
    monkeypatch.setattr(deploy, "execute", execute)
    with pytest.raises(SystemExit, match="permanente"):
        deploy.run("kubectl", "apply", "-f", "-")
    assert len(calls) == 1  # reintentar un YAML roto no lo arregla
    assert deploy.RETRY_LOG == []


def test_transitorio_se_reintenta_y_queda_registrado(monkeypatch):
    execute, calls = fake([
        (1, "", "Unable to connect to the server: net/http: TLS handshake timeout"),
        (0, "ok", ""),
    ])  # fmt: skip
    monkeypatch.setattr(deploy, "execute", execute)
    assert deploy.run("kubectl", "get", "pods") == "ok"
    assert len(calls) == 2
    assert len(deploy.RETRY_LOG) == 1


def test_caida_de_buildkit_es_transitoria(monkeypatch):
    execute, calls = fake([
        (1, "", "ERROR: failed to solve: frontend grpc server closed unexpectedly"),
        (0, "sha256:abc", ""),
    ])  # fmt: skip
    monkeypatch.setattr(deploy, "execute", execute)
    assert deploy.run("docker", "build", ".") == "sha256:abc"
    assert len(calls) == 2


def test_transitorio_tiene_tope(monkeypatch):
    execute, calls = fake([(1, "", "dial tcp: connection refused")])
    monkeypatch.setattr(deploy, "execute", execute)
    with pytest.raises(SystemExit, match="3 intentos agotados"):
        deploy.run("kubectl", "get", "pods", attempts=3)
    assert len(calls) == 3
