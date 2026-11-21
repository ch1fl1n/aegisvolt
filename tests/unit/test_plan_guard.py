"""Guardia R7: un plan de un workspace no puede destruir recursos de otro ambiente."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("plan_guard", ROOT / "scripts" / "plan_guard.py")
plan_guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_guard)


def _change(address: str, name: str, actions: list[str]) -> dict:
    return {"address": address, "change": {"actions": actions, "before": {"name": name}}}


def test_borrar_en_el_mismo_ambiente_se_permite():
    plan = {"resource_changes": [_change("a.t", "aegisvolt-billing-dev", ["delete", "create"])]}
    assert plan_guard.foreign_deletes(plan, "dev") == []


def test_borrar_otro_ambiente_se_bloquea():
    plan = {
        "resource_changes": [
            _change("a.ok", "aegisvolt-billing-dev", ["delete"]),
            _change("a.bad", "aegisvolt-billing-prod", ["delete"]),
            _change("a.new", "aegisvolt-flags-prod", ["create"]),  # crear no es destruir
        ]
    }
    assert plan_guard.foreign_deletes(plan, "dev") == ["a.bad (aegisvolt-billing-prod)"]
