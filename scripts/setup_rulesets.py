"""Crea o actualiza el ruleset de las ramas dev/test/prod en GitHub (idempotente).

Uso (con `gh auth login` hecho y las ramas ya publicadas):
    uv run python scripts/setup_rulesets.py            # aplica
    uv run python scripts/setup_rulesets.py --dry-run  # solo muestra qué haría

Lee .github/rulesets/protected-branches.json, la MISMA fuente que revisa el profesor, y usa
la API de rulesets. Proyecto individual: el PR exige 0 aprobaciones porque GitHub no deja
aprobar tu propio PR; lo que bloquea el merge son los 6 checks obligatorios. Sin bypass:
ni el dueño puede hacer push directo o force push.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULESET = ROOT / ".github" / "rulesets" / "protected-branches.json"


def gh(*args: str, body: str | None = None) -> str:
    proc = subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607 (gh del PATH, sin shell)
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.exit(f"ERROR gh {' '.join(args[:3])}: {proc.stderr.strip()}")
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
    ruleset = json.loads(RULESET.read_text(encoding="utf-8"))
    existing = json.loads(gh("api", f"repos/{repo}/rulesets"))
    match = next((r for r in existing if r["name"] == ruleset["name"]), None)

    method, path = ("PUT", f"repos/{repo}/rulesets/{match['id']}") if match else (
        "POST", f"repos/{repo}/rulesets")  # fmt: skip
    print(f"{repo}: {'actualizar' if match else 'crear'} ruleset '{ruleset['name']}'")
    if args.dry_run:
        print(json.dumps(ruleset, indent=2))
        return 0
    result = json.loads(gh("api", "-X", method, path, "--input", "-", body=json.dumps(ruleset)))
    checks = [c["context"] for r in result["rules"] if r["type"] == "required_status_checks"
              for c in r["parameters"]["required_status_checks"]]  # fmt: skip
    print(f"OK id={result['id']} enforcement={result['enforcement']} checks={checks}")
    print("Recuerda (T3): Settings > Actions > General > 'Require approval for all external")
    print("contributors' para que un fork no corra workflows sin tu aprobación.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
