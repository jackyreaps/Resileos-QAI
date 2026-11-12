"""Tests for the Kuramoto phase field (RES-200 §extension)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.nonconservative import NonConservativeOperator
from resileos.substrate.oscillator import (
    KuramotoField,
    coupling_from_graph,
    empty_coupling,
    golden_ladder,
    golden_weyl,
)
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


def test_large_dt_under_coupling_stays_finite():
    """A single coarse step must not leave the circle."""
    f = KuramotoField(R, kappa=10.0, alpha=1e-3, dt=0.5,
                      random_start=True, seed=0)
    W = np.ones((R, R)) - np.eye(R)
    theta = f.step(epsilon=0.01, W=W, dt=0.5)
    assert np.all(np.isfinite(theta))
    assert np.all(theta >= -np.pi - 1e-6)
    assert np.all(theta <= np.pi + 1e-6)


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


# ── depth and orientation ───────────────────────────────────────────────
def _circ_distance(a, b):
    d = (np.asarray(a) - np.asarray(b) + np.pi) % (2.0 * np.pi) - np.pi
    return float(np.mean(np.abs(d)))


def test_field_has_outward_depth():
    """Default construction is a stack, not a flat ring of r phases."""
    f = KuramotoField(R)
    assert f.depth >= 2
    assert f.orientation == "outward"
    assert f.theta.shape == (R,)
    assert f.level_phases(0).shape == (R,)
    assert f.level_phases(f.depth - 1).shape == (R,)


def test_flat_ring_is_rejected():
    with pytest.raises(ValueError, match="depth"):
        KuramotoField(R, depth=1)


def test_too_few_oscillators_rejected():
    with pytest.raises(ValueError, match="too few"):
        KuramotoField(1)


def test_short_phase_vector_rejected():
    f = KuramotoField(R)
    with pytest.raises(ValueError, match="mis-oriented"):
        f.theta = np.zeros(R - 1)
    with pytest.raises(ValueError, match="mis-oriented"):
        f.set_level_phases(1, np.zeros((1, R)))


def test_wrong_level_axis_rejected():
    """`(r, depth)` is the oscillator axis turned outward. Reject it."""
    f = KuramotoField(R, depth=3)
    swapped = np.zeros((R, f.depth))
    with pytest.raises(ValueError, match="wrong axis"):
        f.set_levels(swapped)
    flat = np.zeros(R)
    with pytest.raises(ValueError, match="no depth axis"):
        f.set_levels(flat)


def test_inward_orientation_rejected():
    with pytest.raises(ValueError, match="outward"):
        KuramotoField(R, orientation="inward")


def test_inner_level_does_not_depend_on_outer():
    """Outward coupling does not write back into level 0."""
    base = np.linspace(-1.0, 1.0, R)
    W = np.ones((R, R)) - np.eye(R)
    kwargs = dict(kappa=1.0, alpha=0.5, dt=0.05, depth=3, seed=0)

    def run(outer_shift):
        f = KuramotoField(R, **kwargs)
        f.set_levels(np.stack([
            base,
            base + outer_shift,
            base - outer_shift,
        ]))
        for _ in range(15):
            f.step(epsilon=0.2, W=W, dt=0.05)
        return f.level_phases(0)

    assert np.allclose(run(1.0), run(-0.7), atol=1e-6)


def test_outer_level_moves_toward_inner():
    """With no within-level edges, the only pull is outward."""
    f = KuramotoField(R, kappa=3.0, alpha=0.5, dt=0.05, depth=3)
    base = np.linspace(-0.8, 0.8, R)
    f.set_levels(np.stack([base, base + 1.0, base + 1.4]))
    W = empty_coupling(R)
    before = _circ_distance(f.level_phases(1), f.level_phases(0))
    for _ in range(40):
        f.step(epsilon=0.2, W=W, dt=0.05)
    after = _circ_distance(f.level_phases(1), f.level_phases(0))
    assert after < before
    # level 2 is outside level 1, so it follows level 1 rather than
    # dragging level 1 back out.
    assert _circ_distance(f.level_phases(2), f.level_phases(1)) < 1.4


def test_coupling_increases_depth_order_in_one_rk4_step_size():
    """
    At a gain the subdivider leaves alone, coupling still raises the
    mean of the per-level order parameters. The #14 substep is a
    safety for a stiffer within-level term; it is not required here.
    """
    f = KuramotoField(
        R, kappa=0.5, alpha=0.5, dt=0.05, depth=3,
        random_start=True, seed=0,
    )
    W = np.ones((R, R)) - np.eye(R)
    epsilon = 0.5
    gain = abs(f.kappa / (f.alpha + epsilon))
    row = float(np.max(np.sum(np.abs(W), axis=1)))
    assert gain * row * f.dt <= 0.2
    R0 = f.depth_order()
    for _ in range(100):
        f.step(epsilon=epsilon, W=W, dt=0.05)
    assert f.depth_order() > R0
    assert f.order_parameter() > 0.0


def test_levels_roundtrip_state_dict():
    f = KuramotoField(R, depth=3, random_start=True, seed=2)
    W = np.ones((R, R)) - np.eye(R)
    f.step(epsilon=0.4, W=W)
    d = f.state_dict()
    g = KuramotoField(R, depth=3)
    g.load_state_dict(d)
    assert np.allclose(g.level_phases(0), f.level_phases(0))
    assert np.allclose(g.level_phases(2), f.level_phases(2))
    assert g.depth == 3
    assert g.orientation == "outward"
