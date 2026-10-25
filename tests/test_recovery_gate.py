"""Tests for F2 recovery → abstention gate."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.oscillator import KuramotoField
from resileos.substrate.recovery_gate import evaluate_recovery_gate
from resileos.substrate.recovery import RecoveryTarget


def test_locked_field_continues():
    f = KuramotoField(r=6, seed=0, alpha=0.5)
    f.omega = np.full(6, f.omega_base / 4.0)
    f.theta = np.zeros(6)
    d = evaluate_recovery_gate(f, target=RecoveryTarget(kind="order", r_min=0.8))
    assert d.action == "CONTINUE"
    assert d.recovery_loss == 0.0


def test_dispersed_field_abstains():
    rng = np.random.default_rng(0)
    f = KuramotoField(r=8, seed=1, alpha=0.5)
    f.theta = rng.uniform(-np.pi, np.pi, size=8)
    d = evaluate_recovery_gate(
        f, target=RecoveryTarget(kind="order", r_min=0.95), loss_max=0.05,
    )
    assert d.action == "ABSTAIN"
