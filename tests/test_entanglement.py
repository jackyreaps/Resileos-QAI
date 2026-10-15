"""Tests for the substrate entanglement probe."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.entanglement import (
    Partition,
    binary_outcome,
    chsh_value,
    correlator,
    mutual_information,
    partition,
    sample_field,
    scan_regimes,
)
from resileos.substrate.oscillator import KuramotoField


# ── partition ───────────────────────────────────────────────────────────
def test_partition_half_covers_all():
    p = partition(8, scheme="half")
    assert set(p.indices_a) | set(p.indices_b) == set(range(8))
    assert set(p.indices_a) & set(p.indices_b) == set()


def test_partition_half_sizes():
    p = partition(8, scheme="half")
    assert p.size_a == 4 and p.size_b == 4


def test_partition_half_odd_r():
    p = partition(7, scheme="half")
    assert p.size_a == 4 and p.size_b == 3
    assert set(p.indices_a) | set(p.indices_b) == set(range(7))


def test_partition_even_odd():
    p = partition(8, scheme="even_odd")
    assert p.indices_a == (0, 2, 4, 6)
    assert p.indices_b == (1, 3, 5, 7)


def test_partition_random_seeded():
    a = partition(8, scheme="random", seed=0)
    b = partition(8, scheme="random", seed=0)
    assert a == b


def test_partition_random_different_seeds():
    a = partition(8, scheme="random", seed=0)
    b = partition(8, scheme="random", seed=1)
    assert a != b


def test_partition_custom():
    p = partition(6, scheme="custom", indices_a=[0, 2, 4],
                  indices_b=[1, 3, 5])
    assert p.indices_a == (0, 2, 4)
    assert p.indices_b == (1, 3, 5)


def test_partition_custom_requires_indices():
    with pytest.raises(ValueError, match="custom"):
        partition(4, scheme="custom")


def test_partition_rejects_small_r():
    with pytest.raises(ValueError, match="r must be"):
        partition(1)


def test_partition_rejects_unknown_scheme():
    with pytest.raises(ValueError, match="unknown scheme"):
        partition(4, scheme="nope")


# ── Partition dataclass ─────────────────────────────────────────────────
def test_partition_dataclass_rejects_overlap():
    with pytest.raises(ValueError, match="disjoint"):
        Partition(indices_a=(0, 1, 2), indices_b=(2, 3, 4))


def test_partition_dataclass_rejects_empty():
    with pytest.raises(ValueError, match="non-empty"):
        Partition(indices_a=(), indices_b=(0, 1))


def test_partition_dataclass_sizes():
    p = Partition(indices_a=(0, 1), indices_b=(2, 3, 4))
    assert p.size_a == 2
    assert p.size_b == 3
    assert p.total == 5


# ── binary_outcome ──────────────────────────────────────────────────────
def test_binary_outcome_plus_one_at_zero_setting():
    theta = np.array([0.0])
    assert binary_outcome(theta, 0.0) == 1


def test_binary_outcome_minus_one_at_pi_setting():
    theta = np.array([0.0])
    assert binary_outcome(theta, np.pi) == -1


def test_binary_outcome_majority_vote():
    theta = np.array([0.0, 0.0, np.pi])
    assert binary_outcome(theta, 0.0) == 1


def test_binary_outcome_returns_int():
    theta = np.array([0.5])
    out = binary_outcome(theta, 0.0)
    assert isinstance(out, int)
    assert out in (-1, 1)


# ── correlator ──────────────────────────────────────────────────────────
def test_correlator_bounded():
    rng = np.random.default_rng(0)
    thetas = rng.uniform(0, 2 * np.pi, size=(200, 8))
    p = partition(8, scheme="half")
    for a in (0.0, np.pi / 2):
        for b in (0.0, np.pi / 2):
            e = correlator(thetas, p, a, b)
            assert -1.0 <= e <= 1.0


def test_correlator_shape_mismatch():
    thetas = np.zeros((10, 4))
    p = partition(8, scheme="half")
    with pytest.raises(ValueError, match="partition covers"):
        correlator(thetas, p, 0.0, 0.0)


# ── chsh_value ──────────────────────────────────────────────────────────
def test_chsh_returns_expected_keys():
    rng = np.random.default_rng(0)
    thetas = rng.uniform(0, 2 * np.pi, size=(100, 8))
    p = partition(8, scheme="half")
    out = chsh_value(thetas, p)
    for k in ("E_a1_b1", "E_a1_b2", "E_a2_b1", "E_a2_b2", "S",
              "classical_bound", "tsirelson_bound",
              "violates_classical"):
        assert k in out


def test_chsh_within_classical_bound_on_random_data():
    rng = np.random.default_rng(0)
    thetas = rng.uniform(0, 2 * np.pi, size=(500, 8))
    p = partition(8, scheme="half")
    out = chsh_value(thetas, p)
    assert abs(out["S"]) <= 2.0 + 1e-9
    assert not out["violates_classical"]


def test_chsh_locked_field_within_classical_bound():
    """A fully locked field is a deterministic hidden-variable model.
    Even at maximum correlation, |S| <= 2."""
    thetas = np.zeros((200, 8))
    thetas[:, :] = 1.234
    p = partition(8, scheme="half")
    out = chsh_value(thetas, p)
    assert abs(out["S"]) <= 2.0 + 1e-9
    assert not out["violates_classical"]


def test_chsh_uncorrelated_field_near_zero():
    rng = np.random.default_rng(42)
    thetas = rng.uniform(0, 2 * np.pi, size=(5000, 8))
    p = partition(8, scheme="half")
    out = chsh_value(thetas, p)
    assert abs(out["S"]) < 0.5


# ── mutual_information ──────────────────────────────────────────────────
def test_mi_nonnegative():
    rng = np.random.default_rng(0)
    thetas = rng.uniform(0, 2 * np.pi, size=(500, 8))
    p = partition(8, scheme="half")
    mi = mutual_information(thetas, p, n_bins=8)
    assert mi >= 0.0


def test_mi_zero_for_independent_uniform():
    rng = np.random.default_rng(0)
    thetas = rng.uniform(0, 2 * np.pi, size=(5000, 8))
    p = partition(8, scheme="half")
    mi = mutual_information(thetas, p, n_bins=8)
    assert mi < 0.1


def test_mi_high_for_locked_field():
    thetas = np.zeros((500, 8))
    thetas[:, :] = np.linspace(0, 2 * np.pi, 500)[:, None]
    p = partition(8, scheme="half")
    mi = mutual_information(thetas, p, n_bins=8)
    assert mi > 1.0


def test_mi_shape_mismatch():
    thetas = np.zeros((10, 4))
    p = partition(8, scheme="half")
    with pytest.raises(ValueError, match="partition covers"):
        mutual_information(thetas, p)


# ── sample_field ────────────────────────────────────────────────────────
def test_sample_field_returns_theta_and_R():
    field = KuramotoField(r=8, ladder="golden_powers", kappa=1.0,
                          alpha=0.5, dt=0.1, random_start=True, seed=0)
    thetas, rs = sample_field(field, n_steps=50, warmup=10)
    assert thetas.shape == (50, 8)
    assert rs.shape == (50,)
    assert np.all(rs >= 0.0) and np.all(rs <= 1.0)


# ── scan_regimes (integration) ──────────────────────────────────────────
def test_scan_regimes_returns_three_regimes():
    out = scan_regimes(r=8, n_samples=200, warmup=50, seed=0)
    assert set(out.keys()) == {"EXPLORING", "MIXED", "LOCKED"}


def test_scan_regimes_all_within_classical_bound():
    """The substrate is a classical phase field. CHSH must not exceed 2."""
    out = scan_regimes(r=8, n_samples=500, warmup=100, seed=0)
    for regime, r in out.items():
        assert abs(r["CHSH"]) <= 2.0 + 1e-9, (
            f"{regime} CHSH={r['CHSH']} exceeds classical bound"
        )
        assert not r["violates_classical"]


def test_scan_regimes_R_monotone_in_kappa():
    """R should increase with kappa (more coupling -> more order)."""
    out = scan_regimes(r=8, n_samples=300, warmup=100, seed=0)
    assert out["EXPLORING"]["R_mean"] <= out["MIXED"]["R_mean"]
    assert out["MIXED"]["R_mean"] <= out["LOCKED"]["R_mean"]


def test_scan_regimes_MI_higher_when_locked():
    out = scan_regimes(r=8, n_samples=500, warmup=100, seed=0)
    assert out["LOCKED"]["MI"] > out["EXPLORING"]["MI"]


def test_scan_regimes_keys():
    out = scan_regimes(r=8, n_samples=100, warmup=20, seed=0)
    for r in out.values():
        for k in ("kappa", "R_mean", "R_std", "CHSH", "correlators",
                  "MI", "violates_classical", "interpretation"):
            assert k in r
