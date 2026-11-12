"""Suite constants and the default-scale outward Kuramoto step."""
import math

import numpy as np
import pytest

from resileos.state_dtype import state_dtype
from resileos.substrate.oscillator import PHI as OSC_PHI
from resileos.substrate.oscillator import KuramotoField
from resileos.substrate.suite_constants import (
    HEALING,
    MAGNETIC_PHASE,
    PHI,
    outward_weight,
)

R = 8


def test_suite_constants_match_the_recorded_numbers():
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    assert PHI == phi
    assert OSC_PHI is PHI
    assert HEALING == 39.5
    assert MAGNETIC_PHASE == 5.116
    assert outward_weight(1.0) == 1.0 / PHI
    assert outward_weight() == 1.0 / PHI


def test_healing_scale_multiplies_the_unit_weight():
    """The recovery scale is an argument, not a second copy of the weight."""
    assert outward_weight(HEALING) == (1.0 / PHI) * HEALING
    assert outward_weight(HEALING) != outward_weight(1.0)


def _literal_weight(scale: float = 1.0) -> float:
    """φ^{-1} at scale 1, computed here rather than via outward_weight."""
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    unit = float(phi ** -1)
    if float(scale) == 1.0:
        return unit
    return unit * float(scale)


def _reference_step(levels, omega, kappa, alpha, epsilon, W, dt, scale=1.0):
    """Depth stack step with the merged outward literal φ^{-1}, times scale.

    Mirrors KuramotoField.step on main: inner RK4, then outward-only
    RK4 on levels 1.. with weight φ^{-1} when scale is 1.
    """
    dtype = state_dtype()
    levels = np.asarray(levels, dtype=dtype).copy()
    omega_state = np.asarray(omega, dtype=dtype)
    W_in = np.asarray(W)
    depth, r = levels.shape
    gain_abs = abs(kappa / (alpha + float(epsilon)))
    row = float(np.max(np.sum(np.abs(W_in), axis=1))) if r else 0.0
    max_phase = 0.2
    nsub = 1
    if gain_abs * row * dt > max_phase:
        nsub = int(math.ceil((gain_abs * row * dt) / max_phase))
        nsub = max(1, min(nsub, 20000))
    gain = kappa / (alpha + float(epsilon))
    weight = _literal_weight(scale)
    h = float(dt) / int(nsub)

    def wrap(theta):
        return ((theta + np.pi) % (2.0 * np.pi)) - np.pi

    def dtheta(theta, coupling, omega_vec):
        diff = theta[None, :] - theta[:, None]
        coupled = (coupling * np.sin(diff)).sum(axis=1)
        return omega_vec + gain * coupled

    def rk4(theta, coupling, omega_vec, step):
        k1 = dtheta(theta, coupling, omega_vec)
        k2 = dtheta(theta + 0.5 * step * k1, coupling, omega_vec)
        k3 = dtheta(theta + 0.5 * step * k2, coupling, omega_vec)
        k4 = dtheta(theta + step * k3, coupling, omega_vec)
        return theta + (step / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    if nsub == 1:
        inner_w = np.asarray(W_in, dtype=dtype)
        theta = np.asarray(levels[0], dtype=dtype)
        levels[0] = np.asarray(
            wrap(rk4(theta, inner_w, omega_state, dt)), dtype=dtype
        )
    else:
        theta = np.asarray(levels[0], dtype=np.float64)
        coupling = np.asarray(W_in, dtype=np.float64)
        for _ in range(nsub):
            theta = wrap(rk4(theta, coupling, omega_state, h))
        levels[0] = np.asarray(theta, dtype=dtype)

    levels64 = np.asarray(levels, dtype=np.float64)
    coupling = np.asarray(W_in, dtype=np.float64)
    omega0 = np.asarray(omega_state, dtype=np.float64)
    phi = (1.0 + math.sqrt(5.0)) / 2.0

    def deriv(phases, level, inner):
        diff = phases[None, :] - phases[:, None]
        within = (coupling * np.sin(diff)).sum(axis=1)
        omega_l = omega0 * (phi ** (-int(level)))
        pull = weight * np.sin(inner - phases)
        return omega_l + gain * within + gain * pull

    def rk4_outer(phases, level, inner):
        k1 = deriv(phases, level, inner)
        k2 = deriv(phases + 0.5 * h * k1, level, inner)
        k3 = deriv(phases + 0.5 * h * k2, level, inner)
        k4 = deriv(phases + h * k3, level, inner)
        return phases + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    for level in range(1, depth):
        phases = levels64[level].copy()
        inner = levels64[level - 1]
        for _ in range(int(nsub)):
            phases = wrap(rk4_outer(phases, level, inner))
        levels64[level] = phases
    levels64[0] = np.asarray(levels[0], dtype=np.float64)
    return np.asarray(levels64, dtype=dtype)


def _run_pair(scale, *, kappa, alpha, dt, epsilon, steps, seed, depth=2):
    field = KuramotoField(
        R, kappa=kappa, alpha=alpha, dt=dt, depth=depth,
        random_start=True, seed=seed, scale=scale,
    )
    W = np.ones((R, R)) - np.eye(R)
    gain = abs(field.kappa / (field.alpha + epsilon))
    row = float(np.max(np.sum(np.abs(W), axis=1)))
    got = []
    ref = []
    levels = np.stack([field.level_phases(i) for i in range(depth)])
    omega = field.omega.copy()
    for _ in range(steps):
        field.step(epsilon=epsilon, W=W, dt=dt)
        levels = _reference_step(
            levels, omega, kappa, alpha, epsilon, W, dt, scale=scale,
        )
        got.append(np.stack([field.level_phases(i) for i in range(depth)]))
        ref.append(levels.copy())
    subdivider_idle = gain * row * dt <= 0.2
    return np.stack(got), np.stack(ref), subdivider_idle


def test_default_scale_depth2_step_matches_phi_inverse():
    """Default scale keeps the merged outward weight φ^{-1}.

    The within-level gain here stays at or under 0.2 rad, so the #14
    subdivider stays idle, as in the cross-level order test.
    """
    got, ref, idle = _run_pair(
        1.0, kappa=0.5, alpha=0.5, dt=0.05, epsilon=0.5, steps=5, seed=0,
    )
    assert idle
    assert np.array_equal(got, ref)
    explicit = KuramotoField(R, kappa=0.5, alpha=0.5, dt=0.05, depth=2)
    assert explicit.scale == 1.0
    assert outward_weight(explicit.scale) == 1.0 / PHI


def test_default_scale_matches_when_the_subdivider_runs():
    got, ref, idle = _run_pair(
        1.0, kappa=10.0, alpha=1e-3, dt=0.5, epsilon=0.01, steps=2, seed=1,
    )
    assert idle is False
    assert np.array_equal(got, ref)


def test_healing_scale_changes_only_the_outer_level():
    base = KuramotoField(
        R, kappa=0.5, alpha=0.5, dt=0.05, depth=2,
        random_start=True, seed=0, scale=1.0,
    )
    healed = KuramotoField(
        R, kappa=0.5, alpha=0.5, dt=0.05, depth=2,
        random_start=True, seed=0, scale=HEALING,
    )
    W = np.ones((R, R)) - np.eye(R)
    base.step(epsilon=0.5, W=W, dt=0.05)
    healed.step(epsilon=0.5, W=W, dt=0.05)
    assert np.array_equal(healed.level_phases(0), base.level_phases(0))
    assert not np.array_equal(healed.level_phases(1), base.level_phases(1))
    got, ref, idle = _run_pair(
        HEALING, kappa=0.5, alpha=0.5, dt=0.05, epsilon=0.5, steps=3, seed=4,
    )
    assert idle
    assert np.array_equal(got, ref)


@pytest.mark.parametrize("depth", [0, 1, -1])
def test_depth_below_two_is_rejected(depth):
    with pytest.raises(ValueError, match="depth"):
        KuramotoField(R, depth=depth)


@pytest.mark.parametrize("r", [0, 1])
def test_fewer_than_two_oscillators_is_rejected(r):
    with pytest.raises(ValueError, match="r must be >= 2"):
        KuramotoField(r)


@pytest.mark.parametrize("orientation", ["inward", "both", "reverse", "OUTWARD", ""])
def test_orientation_other_than_outward_is_rejected(orientation):
    with pytest.raises(ValueError, match="outward"):
        KuramotoField(R, orientation=orientation)


def test_outward_orientation_is_accepted():
    field = KuramotoField(R, orientation="outward")
    assert field.orientation == "outward"
    assert field.depth == 2
    assert field.theta.shape == (R,)
