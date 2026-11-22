"""Guardia del plan de Terraform (R7): bloquea un plan que destruya recursos de OTRO ambiente.

Uso (después de `terraform plan -out=plan.out`):
    terraform show -json plan.out > plan.json
    python scripts/plan_guard.py plan.json --workspace dev

Regla: una acción `delete` sobre un recurso cuyo nombre/ID no termina en `-<workspace>`
significa que el plan toca otro ambiente (workspace equivocado, variable mal puesta...).
Sale con código 1 y el PR no se puede fusionar. Solo librería estándar (corre en cualquier runner).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

NAME_KEYS = ("name", "bucket", "function_name", "cluster_name", "table_name", "log_group_name")


def resource_name(change: dict) -> str:
    before = change.get("change", {}).get("before") or {}
    tags = before.get("tags") or {}
    for key in NAME_KEYS:
        if isinstance(before.get(key), str):
            return before[key]
    return tags.get("Name") or change.get("address", "")


def foreign_deletes(plan: dict, workspace: str) -> list[str]:
    bad = []
    for change in plan.get("resource_changes", []):
        if "delete" not in change.get("change", {}).get("actions", []):
            continue
        name = resource_name(change)
        if not name.endswith(f"-{workspace}"):
            bad.append(f"{change['address']} ({name})")
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan_json", type=Path)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan_json.read_text(encoding="utf-8-sig"))  # tolera BOM
    deletes = sum(
        "delete" in c.get("change", {}).get("actions", []) for c in plan.get("resource_changes", [])
    )
    bad = foreign_deletes(plan, args.workspace)
    if bad:
        print(f"BLOQUEADO: el plan de '{args.workspace}' destruye recursos de otro ambiente:")
        for item in bad:
            print(f"  - {item}")
        return 1
    print(f"OK: {deletes} destrucciones, todas dentro del ambiente '{args.workspace}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
