"""E2E: requieren Floci + los 4 servicios (`uv run python scripts/run_services.py`)."""

import os
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8000")


def _dotenv(key: str) -> str | None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


@pytest.fixture(scope="session")
def admin_token() -> str:
    token = os.environ.get("ADMIN_TOKEN") or _dotenv("ADMIN_TOKEN")
    if not token:
        pytest.skip("Falta ADMIN_TOKEN en .env")
    return token


@pytest.fixture(scope="session")
def http() -> httpx.Client:
    client = httpx.Client(timeout=20)
    try:
        client.get(f"{GATEWAY}/readyz").raise_for_status()
    except httpx.HTTPError:
        client.close()
        pytest.skip("El gateway no responde: levanta todo con scripts/run_services.py")
    yield client
    client.close()
