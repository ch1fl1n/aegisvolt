"""Carga datos de demostración por las APIs de los servicios (nunca directo a las tablas).

Uso (con los servicios arriba: run_services.py o compose.apps.yaml):
    uv run python scripts/seed.py
    uv run python scripts/seed.py --gateway http://localhost:8000 --reset-flags

Es idempotente: se puede correr las veces que quieras (PUT = crear o reemplazar).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent

STATIONS = {
    "st-norte": {"c1": 150, "c2": 50},
    "st-centro": {"c1": 350, "c2": 150, "c3": 22},
    "st-sur": {"c1": 50},
}
WALLETS = {
    "acc-demo": 50_000,  # 500,00: alcanza para varias cargas
    "acc-pobre": 100,  # 1,00: para el escenario de fondos insuficientes
}
FLAGS = (
    "ENABLE_DYNAMIC_SURGE_PRICING",
    "ENABLE_FAST_CHARGE_BOOST",
    "SIMULATE_CHARGER_HARDWARE_FAULT",
)


def admin_token() -> str | None:
    if token := os.environ.get("ADMIN_TOKEN"):
        return token
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ADMIN_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Datos de demo de AegisVolt")
    parser.add_argument("--reservations", default="http://localhost:8001")
    parser.add_argument("--billing", default="http://localhost:8002")
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--reset-flags", action="store_true", help="apaga las 3 flags")
    args = parser.parse_args()

    with httpx.Client(timeout=10) as http:
        try:
            for station, connectors in STATIONS.items():
                for connector, power in connectors.items():
                    url = f"{args.reservations}/stations/{station}/connectors/{connector}"
                    resp = http.put(url, json={"power_kw": power})
                    if resp.status_code == 409:  # tiene una reserva activa: no se pisa
                        print(f"  = {station}/{connector} reservado, se deja igual")
                        continue
                    resp.raise_for_status()
                    print(f"  + conector {station}/{connector} {power} kW")
            for account, cents in WALLETS.items():
                url = f"{args.billing}/wallets/{account}"
                http.put(url, json={"balance_cents": cents}).raise_for_status()
                print(f"  + billetera {account} saldo {cents / 100:.2f}")
            if args.reset_flags:
                token = admin_token()
                if not token:
                    sys.exit("ERROR: --reset-flags necesita ADMIN_TOKEN (.env)")
                for name in FLAGS:
                    query = f"mutation {{ setFlag(name: {name}, enabled: false) {{ enabled }} }}"
                    resp = http.post(
                        f"{args.gateway}/graphql",
                        json={"query": query},
                        headers={"x-admin-token": token},
                    )
                    resp.raise_for_status()
                    if "errors" in resp.json():
                        sys.exit(f"ERROR al apagar {name}: {resp.json()['errors']}")
                    print(f"  + flag {name} = false")
        except httpx.HTTPError as exc:
            sys.exit(f"ERROR: {exc}. ¿Están los servicios arriba?")
    print("OK datos de demo cargados")


if __name__ == "__main__":
    main()
