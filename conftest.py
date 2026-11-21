"""Hooks comunes de pytest para todo el repo.

En local, las pruebas de integración/e2e se SALTAN si Floci no está arriba (cómodo).
En CI eso sería peligroso: un check "verde" con todo saltado no prueba nada.
Con AEGIS_STRICT_SKIPS=1 (lo pone el workflow) cualquier skip se convierte en falla.
"""

import os

import pytest

STRICT = os.environ.get("AEGIS_STRICT_SKIPS") == "1"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if STRICT and report.skipped and not hasattr(report, "wasxfail"):
        report.outcome = "failed"
        report.longrepr = f"Skip no permitido en CI (AEGIS_STRICT_SKIPS=1): {report.longrepr}"
