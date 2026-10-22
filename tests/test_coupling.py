"""Tests for CouplingField and CoupledPacket (RES-318 §4, §6, §8).

Invariants from RES-318 §8 covered here:

    1. Phase differences are informative  — test_phase_difference_antisymmetric,
                                            test_R_varies_with_kappa
    4. Coupling field converges          — test_high_kappa_synchronizes

Invariants 2, 3, 5 (monitor correlation, residue divergence, group basins)
require actual ResidualCore instances and are deferred to test_engine_group.py.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.hierarchy import HierarchicalPacket
from resileos.substrate.coupling import CouplingField, CoupledPacket, PHI, TWO_PI


# ── helpers ────────────────────────────────────────────────────────────
def _make_packet(level=1, dim=16, span=(0, 4), child_count=4):
    rng = np.random.default_rng(level + dim)
    hv = rng.standard_normal(dim) + 1j * rng.standard_normal(dim)
    hv = hv / np.linalg.norm(hv)
    return HierarchicalPacket(
        level=level, hv=hv, span_start=span[0], span_end=span[1],
        child_count=child_count,
    )


def _run(field, n_steps, drives_fn=None, W=None):
    """Advance the field n_steps times, optionally with per-step drives."""
    for t in range(n_steps):
        d = drives_fn(t) if drives_fn is not None else None
        field.step(drives=d, W=W)


# ══════════════════════════════════════════════════════════════════════
# CouplingField — construction
# ══════════════════════════════════════════════════════════════════════
def test_rejects_zero_engines():
    with pytest.raises(ValueError, match="n_engines"):
        CouplingField(n_engines=0)


def test_rejects_negative_kappa():
    with pytest.raises(ValueError, match="kappa"):
        CouplingField(n_engines=3, kappa=-0.1)


def test_rejects_zero_dt():
    with pytest.raises(ValueError, match="dt"):
        CouplingField(n_engines=3, dt=0.0)


def test_rejects_unknown_ladder():
    with pytest.raises(ValueError, match="ladder"):
        CouplingField(n_engines=3, ladder="fibonacci")


def test_theta_shape():
    f = CouplingField(n_engines=3)
    assert f.theta.shape == (3,)


def test_omega_shape():
    f = CouplingField(n_engines=4)
    assert f.omega.shape == (4,)


def test_omega_uniform_by_default():
    f = CouplingField(n_engines=3, omega_base=TWO_PI)
    assert np.allclose(f.omega, TWO_PI)


def test_omega_golden_powers():
    f = CouplingField(n_engines=3, omega_base=1.0, ladder="golden_powers")
    expected = np.array([1.0, 1.0 / PHI, 1.0 / PHI ** 2])
    assert np.allclose(f.omega, expected)


def test_random_start_false_gives_zero_phases():
    f = CouplingField(n_engines=4, random_start=False)
    assert np.allclose(f.theta, 0.0)


# ══════════════════════════════════════════════════════════════════════
# CouplingField — order parameter
# ══════════════════════════════════════════════════════════════════════
def test_order_parameter_in_range():
    f = CouplingField(n_engines=4, seed=0)
    R = f.order_parameter()
    assert 0.0 <= R <= 1.0 + 1e-9


def test_order_parameter_locked():
    # random_start=False -> all phases 0 -> R = 1
    f = CouplingField(n_engines=4, random_start=False)
    assert f.order_parameter() == pytest.approx(1.0)


def test_order_parameter_scattered():
    # Manually set phases evenly spaced around the circle
    f = CouplingField(n_engines=4, random_start=False)
    f._theta = np.array([0.0, np.pi / 2, np.pi, 3 * np.pi / 2])
    # Evenly spaced -> R should be ~0
    assert f.order_parameter() < 0.1


def test_order_parameter_single_engine_is_one():
    f = CouplingField(n_engines=1, seed=0)
    assert f.order_parameter() == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════════
# CouplingField — phase difference
# ══════════════════════════════════════════════════════════════════════
def test_phase_difference_self_is_zero():
    f = CouplingField(n_engines=3, seed=0)
    for i in range(3):
        assert f.phase_difference(i, i) == pytest.approx(0.0)


def test_phase_difference_antisymmetric():
    f = CouplingField(n_engines=4, seed=0)
    for i in range(4):
        for j in range(4):
            assert f.phase_difference(i, j) == pytest.approx(
                -f.phase_difference(j, i), abs=1e-9
            ) or abs(
                abs(f.phase_difference(i, j) + f.phase_difference(j, i))
                - TWO_PI
            ) < 1e-9


def test_phase_difference_wrapped():
    f = CouplingField(n_engines=2, random_start=False)
    f._theta = np.array([3.0, -3.0])  # difference is 6.0 > pi
    d = f.phase_difference(0, 1)
    # 6.0 mod 2pi = 6.0 - 2pi = -0.283, wrapped to (-pi, pi]
    assert -np.pi <= d <= np.pi
    assert d == pytest.approx(6.0 - TWO_PI, abs=1e-9)


def test_phase_difference_rejects_out_of_range():
    f = CouplingField(n_engines=3)
    with pytest.raises(IndexError, match="i=5"):
        f.phase_difference(5, 0)
    with pytest.raises(IndexError, match="j=5"):
        f.phase_difference(0, 5)


# ══════════════════════════════════════════════════════════════════════
# CouplingField — coupling matrix
# ══════════════════════════════════════════════════════════════════════
def test_coupling_matrix_shape():
    f = CouplingField(n_engines=4, seed=0)
    M = f.coupling_matrix()
    assert M.shape == (4, 4)


def test_coupling_matrix_diagonal_zero():
    f = CouplingField(n_engines=4, seed=0)
    M = f.coupling_matrix()
    assert np.allclose(np.diag(M), 0.0, atol=1e-9)


def test_coupling_matrix_matches_phase_difference():
    f = CouplingField(n_engines=3, seed=0)
    M = f.coupling_matrix()
    for i in range(3):
        for j in range(3):
            assert M[i, j] == pytest.approx(
                f.phase_difference(i, j), abs=1e-9
            )


def test_coupling_matrix_absolute_antisymmetric():
    f = CouplingField(n_engines=4, seed=0)
    M = f.coupling_matrix()
    assert np.allclose(np.abs(M), np.abs(M.T), atol=1e-9)


# ══════════════════════════════════════════════════════════════════════
# CouplingField — step behavior
# ══════════════════════════════════════════════════════════════════════
def test_step_advances_phase():
    f = CouplingField(n_engines=1, random_start=False, omega_base=1.0, dt=0.1)
    theta_0 = f.theta[0]
    f.step()
    theta_1 = f.theta[0]
    assert theta_1 != theta_0
    # With single engine, no coupling; dtheta = omega = 1.0, dt=0.1
    assert theta_1 - theta_0 == pytest.approx(0.1, abs=1e-9)


def test_step_with_zero_drive_and_no_coupling_advances_by_omega():
    f = CouplingField(
        n_engines=3, random_start=False, omega_base=1.0, dt=0.1, kappa=0.0
    )
    f.step(drives=np.zeros(3))
    # All phases advance by 0.1 (no coupling, all same omega)
    assert np.allclose(f.theta, 0.1)


def test_step_rejects_bad_drives_shape():
    f = CouplingField(n_engines=3)
    with pytest.raises(ValueError, match="drives shape"):
        f.step(drives=np.array([0.1, 0.2]))


def test_step_rejects_bad_W_shape():
    f = CouplingField(n_engines=3)
    with pytest.raises(ValueError, match="W shape"):
        f.step(W=np.ones((2, 2)))


def test_step_wraps_theta():
    f = CouplingField(
        n_engines=1, random_start=False, omega_base=100.0, dt=1.0
    )
    # After one step theta = 100, must wrap to (-pi, pi]
    f.step()
    assert -np.pi <= f.theta[0] <= np.pi


def test_high_kappa_synchronizes():
    """RES-318 §8 invariant 4: coupling field converges under high kappa."""
    f = CouplingField(
        n_engines=4, kappa=10.0, dt=0.1, random_start=True, seed=0
    )
    initial_R = f.order_parameter()
    for _ in range(200):
        f.step()
    final_R = f.order_parameter()
    assert final_R > 0.9, (
        f"high kappa failed to synchronize: initial_R={initial_R:.3f}, "
        f"final_R={final_R:.3f}"
    )


def test_zero_kappa_engines_drift_apart():
    """No coupling + random drive -> engines drift apart."""
    f = CouplingField(
        n_engines=4, kappa=0.0, dt=0.1, random_start=False, seed=0
    )
    assert f.order_parameter() == pytest.approx(1.0)  # all start at 0

    rng = np.random.default_rng(0)
    for _ in range(200):
        f.step(drives=rng.standard_normal(4) * 0.5)

    # Without coupling, phases drift apart; R should be well below 1
    assert f.order_parameter() < 0.9


def test_R_varies_with_kappa():
    """RES-318 §8 invariant 1: R is informative (not degenerate)."""
    rng = np.random.default_rng(0)
    drives = rng.standard_normal((200, 4)) * 0.5

    f_low = CouplingField(
        n_engines=4, kappa=0.1, dt=0.1, random_start=False, seed=0
    )
    for t in range(200):
        f_low.step(drives=drives[t])
    R_low = f_low.order_parameter()

    f_high = CouplingField(
        n_engines=4, kappa=10.0, dt=0.1, random_start=False, seed=0
    )
    for t in range(200):
        f_high.step(drives=drives[t])
    R_high = f_high.order_parameter()

    assert R_high > R_low, (
        f"higher kappa should give higher R: "
        f"R_low={R_low:.3f}, R_high={R_high:.3f}"
    )


# ══════════════════════════════════════════════════════════════════════
# CouplingField — determinism and lifecycle
# ══════════════════════════════════════════════════════════════════════
def test_determinism_same_seed():
    a = CouplingField(n_engines=4, seed=42)
    b = CouplingField(n_engines=4, seed=42)
    assert np.allclose(a.theta, b.theta)
    for _ in range(10):
        a.step()
        b.step()
    assert np.allclose(a.theta, b.theta)


def test_different_seeds_differ():
    a = CouplingField(n_engines=4, seed=0)
    b = CouplingField(n_engines=4, seed=1)
    assert not np.allclose(a.theta, b.theta)


def test_reset_restores_initial():
    f = CouplingField(n_engines=4, seed=7)
    theta_0 = f.theta.copy()
    for _ in range(20):
        f.step()
    assert not np.allclose(f.theta, theta_0)
    f.reset()
    assert np.allclose(f.theta, theta_0)


def test_snapshot_keys():
    f = CouplingField(n_engines=3, seed=0)
    s = f.snapshot()
    for k in (
        "n_engines", "kappa", "alpha", "dt", "omega_base",
        "ladder", "random_start", "seed", "theta", "omega", "R",
    ):
        assert k in s
    assert s["n_engines"] == 3
    assert len(s["theta"]) == 3
    assert len(s["omega"]) == 3


# ══════════════════════════════════════════════════════════════════════
# CoupledPacket
# ══════════════════════════════════════════════════════════════════════
def _make_coupled(n=3, K=8, seed=0):
    rng = np.random.default_rng(seed)
    packets = tuple(_make_packet(level=1, dim=16) for _ in range(n))
    phases = tuple(float(x) for x in rng.uniform(-np.pi, np.pi, n))
    R = 0.5
    # Build an antisymmetric matrix from the phases
    raw = np.array(phases)[:, None] - np.array(phases)[None, :]
    M = np.mod(raw + np.pi, TWO_PI) - np.pi
    np.fill_diagonal(M, 0.0)
    residue = tuple(rng.standard_normal(K) for _ in range(n))
    return CoupledPacket(
        packets=packets,
        phases=phases,
        R_shared=R,
        coupling_matrix=M,
        residue_history=residue,
    )


def test_coupled_packet_basic():
    cp = _make_coupled(n=3)
    assert cp.n_engines == 3
    assert len(cp.packets) == 3
    assert len(cp.phases) == 3
    assert 0.0 <= cp.R_shared <= 1.0
    assert cp.coupling_matrix.shape == (3, 3)


def test_coupled_packet_rejects_empty():
    with pytest.raises(ValueError, match="at least one engine"):
        CoupledPacket(
            packets=(),
            phases=(),
            R_shared=0.5,
            coupling_matrix=np.zeros((0, 0)),
            residue_history=(),
        )


def test_coupled_packet_rejects_phases_length_mismatch():
    packets = (_make_packet(), _make_packet())
    with pytest.raises(ValueError, match="phases"):
        CoupledPacket(
            packets=packets,
            phases=(0.0,),  # wrong length
            R_shared=0.5,
            coupling_matrix=np.zeros((2, 2)),
            residue_history=(np.zeros(4), np.zeros(4)),
        )


def test_coupled_packet_rejects_residue_length_mismatch():
    packets = (_make_packet(), _make_packet())
    with pytest.raises(ValueError, match="residue_history"):
        CoupledPacket(
            packets=packets,
            phases=(0.0, 0.0),
            R_shared=0.5,
            coupling_matrix=np.zeros((2, 2)),
            residue_history=(np.zeros(4),),  # wrong length
        )


def test_coupled_packet_rejects_bad_matrix_shape():
    packets = (_make_packet(), _make_packet())
    with pytest.raises(ValueError, match="coupling_matrix shape"):
        CoupledPacket(
            packets=packets,
            phases=(0.0, 0.0),
            R_shared=0.5,
            coupling_matrix=np.zeros((3, 3)),  # wrong shape
            residue_history=(np.zeros(4), np.zeros(4)),
        )


def test_coupled_packet_rejects_nonzero_diagonal():
    packets = (_make_packet(), _make_packet())
    M = np.zeros((2, 2))
    M[0, 0] = 0.1
    with pytest.raises(ValueError, match="diagonal"):
        CoupledPacket(
            packets=packets,
            phases=(0.0, 0.0),
            R_shared=0.5,
            coupling_matrix=M,
            residue_history=(np.zeros(4), np.zeros(4)),
        )


def test_coupled_packet_rejects_non_antisymmetric():
    packets = (_make_packet(), _make_packet())
    M = np.array([[0.0, 0.5], [0.5, 0.0]])  # symmetric, not antisymmetric
    with pytest.raises(ValueError, match="antisymmetric"):
        CoupledPacket(
            packets=packets,
            phases=(0.0, 0.0),
            R_shared=0.5,
            coupling_matrix=M,
            residue_history=(np.zeros(4), np.zeros(4)),
        )


def test_coupled_packet_rejects_R_out_of_range():
    packets = (_make_packet(),)
    with pytest.raises(ValueError, match="R_shared"):
        CoupledPacket(
            packets=packets,
            phases=(0.0,),
            R_shared=1.5,
            coupling_matrix=np.zeros((1, 1)),
            residue_history=(np.zeros(4),),
        )


def test_coupled_packet_rejects_bad_residue_shape():
    packets = (_make_packet(),)
    with pytest.raises(ValueError, match="residue_history"):
        CoupledPacket(
            packets=packets,
            phases=(0.0,),
            R_shared=0.5,
            coupling_matrix=np.zeros((1, 1)),
            residue_history=(np.zeros((4, 4)),),  # 2-D, must be 1-D
        )


def test_coupled_packet_coerces_lists_to_tuples():
    packets = [_make_packet(), _make_packet()]
    phases = [0.0, 1.0]
    residue = [np.zeros(4), np.ones(4)]
    M = np.array([[0.0, 1.0], [-1.0, 0.0]])
    cp = CoupledPacket(
        packets=packets,
        phases=phases,
        R_shared=0.5,
        coupling_matrix=M,
        residue_history=residue,
    )
    assert isinstance(cp.packets, tuple)
    assert isinstance(cp.phases, tuple)
    assert isinstance(cp.residue_history, tuple)


def test_coupled_packet_to_dict():
    cp = _make_coupled(n=3)
    d = cp.to_dict()
    assert d["n_engines"] == 3
    assert len(d["packets"]) == 3
    assert len(d["phases"]) == 3
    assert len(d["residue_history"]) == 3
    # coupling_matrix is (3, 3) list of lists
    assert len(d["coupling_matrix"]) == 3
    assert all(len(row) == 3 for row in d["coupling_matrix"])


def test_coupled_packet_frozen():
    cp = _make_coupled()
    with pytest.raises((AttributeError, Exception)):
        cp.R_shared = 0.9


# ══════════════════════════════════════════════════════════════════════
# Integration: field -> coupled packet
# ══════════════════════════════════════════════════════════════════════
def test_field_state_to_coupled_packet():
    """The field's current state becomes a CoupledPacket."""
    f = CouplingField(n_engines=3, seed=0)
    for _ in range(10):
        f.step()
    packets = tuple(_make_packet() for _ in range(3))
    cp = CoupledPacket(
        packets=packets,
        phases=tuple(f.theta.tolist()),
        R_shared=f.order_parameter(),
        coupling_matrix=f.coupling_matrix(),
        residue_history=tuple(np.zeros(8) for _ in range(3)),
    )
    assert cp.n_engines == 3
    assert np.allclose(
        cp.coupling_matrix, f.coupling_matrix()
    )
