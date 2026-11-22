"""promote() de canary.py: si el rollout del estable falla, nunca deja el tráfico en el canary."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import canary  # noqa: E402


class FakeKube:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail_on = fail_on

    def __call__(self, *args: str, check: bool = True) -> str:
        self.calls.append(args)
        if check and self.fail_on and self.fail_on in args:
            raise SystemExit("timed out waiting for the condition")
        return ""

    def set_weight(self, weight: int) -> None:
        self.calls.append(("weight", str(weight)))


def test_promocion_ok_deja_weight_0_y_canary_apagado():
    kube = FakeKube()
    assert canary.promote(kube, "v9") is True
    assert kube.calls[-2] == ("weight", "0")
    assert kube.calls[-1][-1] == "--replicas=0"


def test_rollout_lento_revierte_y_saca_el_trafico_del_canary():
    kube = FakeKube(fail_on="status")
    assert canary.promote(kube, "v9") is False
    flat = [" ".join(c) for c in kube.calls]
    assert any("rollout undo deployment/graphql-gateway" in c for c in flat)
    assert any("canary-weight=0" in c for c in flat)  # el rollback corta el tráfico
    assert any("--replicas=0" in c for c in flat)
    assert ("weight", "0") not in kube.calls[: flat.index(next(c for c in flat if "undo" in c))]
