"""F2 recovery product tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.oscillator import KuramotoField
from resileos.substrate.recovery import (
    RecoveryTarget,
    circular_distance,
    measure_recovery_product,
    recovery_loss,
    recovery_time,
)


def test_recovery_loss_order_zero_when_locked():
    theta = np.zeros(8)
    t = RecoveryTarget(kind="order", r_min=0.9)
    assert recovery_loss(theta, t) == 0.0


def test_recovery_loss_order_positive_when_dispersed():
    rng = np.random.default_rng(0)
    theta = rng.uniform(-np.pi, np.pi, size=8)
    t = RecoveryTarget(kind="order", r_min=0.95)
    assert recovery_loss(theta, t) > 0.0


def test_circular_distance_identical():
    theta = np.array([0.1, -0.2, 0.3])
    assert circular_distance(theta, theta) < 1e-12


def test_recovery_time_zero_if_already_ok():
    f = KuramotoField(r=6, seed=0)
    f.theta = np.zeros(6)
    t = RecoveryTarget(kind="order", r_min=0.5)
    assert recovery_time(f, np.zeros(6), t, max_steps=10) == 0


def test_recovery_time_recovers_under_coupling():
    r = 8
    W = (2.0 / (r - 1)) * (np.ones((r, r)) - np.eye(r))
    f = KuramotoField(r=r, seed=1, alpha=0.5)
    f.omega = np.full(r, f.omega_base / 4.0)
    f.theta = np.random.default_rng(1).uniform(-np.pi, np.pi, size=r)
    for _ in range(300):
        f.step(0.0, W=W)
    assert f.order_parameter() > 0.8
    locked = f.theta.copy()
    f.theta = locked
    t = RecoveryTarget(kind="order", r_min=0.8)
    pert = np.ones(r) * 0.5
    steps = recovery_time(f, pert, t, max_steps=300, W=W)
    assert steps is not None
    assert steps >= 0


def test_measure_recovery_product_runs():
    report = measure_recovery_product(
        r=6, n_trials=5, max_steps=200, seed=0, r_min=0.8,
    )
    assert report["n_trials"] == 5
    assert 0.0 <= report["recovery_rate"] <= 1.0
    assert "A1" in report["assumptions"][0]
