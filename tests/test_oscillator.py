"""Tests for the Kuramoto phase field (RES-200 §extension)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.oscillator import (
    KuramotoField, golden_ladder, golden_weyl, coupling_from_graph,
    empty_coupling, PHI,
)
from resileos.substrate.nonconservative import NonConservativeOperator
from resileos.substrate.phasor import PhasorGraph


R = 8


# ── ladders ─────────────────────────────────────────────────────────────
def test_golden_ladder_shape():
    omega = golden_ladder(R)
    assert omega.shape == (R,)
    assert omega.min() >= 0.0
    assert omega.max() < 2.0 * np.pi


def test_golden_ladder_irrational():
    """No pair of ladder entries forms a small-integer rational ratio
    exactly (within floating point)."""
    omega = golden_ladder(6)
    for i in range(6):
        for j in range(i + 1, 6):
            r = omega[i] / (omega[j] + 1e-12)
            # r should not be a small-integer fraction exactly
            assert not np.isclose(r * 3.0, round(r * 3.0), atol=1e-12) or \
                   not np.isclose(r * 5.0, round(r * 5.0), atol=1e-12)


def test_golden_weyl_shape():
    omega = golden_weyl(R)
    assert omega.shape == (R,)
    assert omega[0] == 0.0
    assert omega.max() < 2.0 * np.pi


def test_unknown_ladder_raises():
    with pytest.raises(ValueError, match="ladder"):
        KuramotoField(R, ladder="nonsense")


# ── construction ────────────────────────────────────────────────────────
def test_field_constructs():
    f = KuramotoField(R)
    assert f.r == R
    assert f.theta.shape == (R,)
    assert np.allclose(f.theta, 0.0)


def test_field_rejects_bad_alpha():
    with pytest.raises(ValueError, match="alpha"):
        KuramotoField(R, alpha=0.0)


def test_field_rejects_bad_dt():
    with pytest.raises(ValueError, match="dt"):
        KuramotoField(R, dt=0.0)


def test_field_random_start_is_seeded():
    a = KuramotoField(R, random_start=True, seed=1)
    b = KuramotoField(R, random_start=True, seed=1)
    c = KuramotoField(R, random_start=True, seed=2)
    assert np.allclose(a.theta, b.theta)
    assert not np.allclose(a.theta, c.theta)


# ── dynamics ────────────────────────────────────────────────────────────
def test_no_coupling_theta_advances_at_omega():
    """With W = 0, each theta evolves at its own omega_i * dt."""
    f = KuramotoField(R, kappa=0.0, dt=0.05)
    W = empty_coupling(R)
    theta0 = f.theta.copy()
    theta1 = f.step(epsilon=1.0, W=W, dt=0.05)
    expected = theta0 + f.omega * 0.05
    # RK4 of a constant derivative is exact
    assert np.allclose(theta1, ((expected + np.pi) % (2 * np.pi)) - np.pi,
                       atol=1e-9)


def test_coupling_increases_order_parameter():
    """From random start, high coupling should drive R up over time."""
    rng = np.random.default_rng(0)
    f = KuramotoField(R, kappa=10.0, alpha=1e-3, dt=0.05,
                      random_start=True, seed=0)
    W = np.ones((R, R)) - np.eye(R)
    R0 = f.order_parameter()
    for _ in range(200):
        f.step(epsilon=0.01, W=W, dt=0.05)   # small epsilon -> strong coupling
    R1 = f.order_parameter()
    assert R1 > R0, f"R did not increase: {R0} -> {R1}"


def test_no_coupling_keeps_R_low_over_time():
    """With W = 0 and random start, R should stay near its initial value
    or oscillate; it should not converge to 1."""
    f = KuramotoField(R, kappa=0.0, dt=0.05, random_start=True, seed=0)
    W = empty_coupling(R)
    for _ in range(200):
        f.step(epsilon=0.01, W=W, dt=0.05)
    R_end = f.order_parameter()
    assert R_end < 0.9, f"R drifted to {R_end} with no coupling"


def test_epsilon_controls_coupling_strength():
    """Small epsilon (Option A) means strong coupling."""
    W = np.ones((R, R)) - np.eye(R)

    f_low = KuramotoField(R, kappa=1.0, alpha=1e-3, dt=0.05,
                          random_start=True, seed=0)
    f_high = KuramotoField(R, kappa=1.0, alpha=1e-3, dt=0.05,
                           random_start=True, seed=0)

    for _ in range(100):
        f_low.step(epsilon=0.01, W=W, dt=0.05)
        f_high.step(epsilon=10.0, W=W, dt=0.05)

    # Both start from the same random state; the low-epsilon field has
    # stronger coupling and should order more.
    assert f_low.order_parameter() > f_high.order_parameter()


def test_order_parameter_bounded():
    f = KuramotoField(R, random_start=True, seed=0)
    for _ in range(50):
        f.step(epsilon=1.0, W=np.ones((R, R)) - np.eye(R))
    R_val = f.order_parameter()
    assert 0.0 <= R_val <= 1.0 + 1e-9


def test_theta_wrapped_to_pi():
    f = KuramotoField(R, kappa=100.0, dt=0.5, random_start=True, seed=0)
    W = np.ones((R, R)) - np.eye(R)
    for _ in range(100):
        f.step(epsilon=0.001, W=W, dt=0.5)
    assert np.all(f.theta >= -np.pi - 1e-9)
    assert np.all(f.theta <= np.pi + 1e-9)


def test_deterministic():
    def run():
        f = KuramotoField(R, kappa=1.0, dt=0.05, random_start=True, seed=0)
        W = np.ones((R, R)) - np.eye(R)
        for _ in range(20):
            f.step(epsilon=0.5, W=W, dt=0.05)
        return f.theta.copy()
    assert np.array_equal(run(), run())


def test_bad_W_shape_raises():
    f = KuramotoField(R)
    with pytest.raises(ValueError, match="W shape"):
        f.step(epsilon=1.0, W=np.zeros((R + 1, R + 1)))


# ── coupling from graph ─────────────────────────────────────────────────
def test_coupling_from_graph_symmetric():
    g = PhasorGraph(R, hermitian=True)
    rng = np.random.default_rng(0)
    for i in range(R):
        for j in range(i + 1, R):
            g.set_edge(i, j, amplitude=float(rng.random()),
                       phase=float(rng.uniform(0, 2 * np.pi)))
    W = coupling_from_graph(g)
    assert np.allclose(W, W.T)
    assert np.allclose(np.diag(W), 0.0)
    assert np.all(W >= 0.0)


def test_coupling_from_graph_empty():
    g = PhasorGraph(R, hermitian=True)
    W = coupling_from_graph(g)
    assert np.allclose(W, 0.0)


# ── operator integration ────────────────────────────────────────────────
def test_operator_without_oscillator_uses_linear_drive():
    op = NonConservativeOperator(R, mode="non-conservative")
    for i in range(20):
        op.update(F_res=0.5, DeltaS=0.3, mu=i % 2)
    assert op.using_oscillator is False


def test_operator_with_oscillator_delegates_theta():
    field = KuramotoField(R, kappa=1.0, dt=0.1, random_start=True, seed=0)
    op = NonConservativeOperator(R, mode="non-conservative",
                                 oscillator=field)
    W = np.ones((R, R)) - np.eye(R)
    op.attach_coupling(W)

    theta_before = op.theta.copy()
    op.update(F_res=0.5, DeltaS=0.3, mu=0, epsilon=0.05)
    theta_after = op.theta.copy()

    assert op.using_oscillator is True
    # Theta should have changed (driven by the Kuramoto field)
    assert not np.allclose(theta_before, theta_after)
    # And the operator's order parameter should match the field's
    assert np.isclose(op.order_parameter(), field.order_parameter())


def test_operator_without_epsilon_falls_back_to_linear():
    field = KuramotoField(R, kappa=1.0, random_start=True, seed=0)
    op = NonConservativeOperator(R, mode="non-conservative",
                                 oscillator=field)
    op.update(F_res=0.5, DeltaS=0.3, mu=1)   # no epsilon
    assert op.using_oscillator is False


def test_operator_conservative_ignores_oscillator():
    field = KuramotoField(R, kappa=1.0, random_start=True, seed=0)
    op = NonConservativeOperator(R, mode="conservative",
                                 oscillator=field)
    op.update(F_res=1.0, DeltaS=1.0, mu=1, epsilon=0.01)
    # Conservative mode returns early; theta stays at zero
    assert np.allclose(op.theta, 0.0)
    assert op.using_oscillator is False


def test_operator_state_dict_with_oscillator():
    field = KuramotoField(R, kappa=1.0, random_start=True, seed=0)
    op = NonConservativeOperator(R, mode="non-conservative",
                                 oscillator=field)
    op.attach_coupling(np.ones((R, R)) - np.eye(R))
    for _ in range(5):
        op.update(F_res=0.5, DeltaS=0.3, mu=0, epsilon=0.1)

    d = op.state_dict()
    assert "oscillator" in d
    assert "W" in d

    op2 = NonConservativeOperator(R, mode="non-conservative",
                                  oscillator=KuramotoField(R))
    op2.load_state_dict(d)
    assert np.allclose(op2.theta, op.theta, atol=1e-9)


def test_operator_attach_coupling_validates_shape():
    op = NonConservativeOperator(R, mode="non-conservative")
    with pytest.raises(ValueError, match="W shape"):
        op.attach_coupling(np.zeros((R + 1, R + 1)))
