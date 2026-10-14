"""Tests for the reaper pass."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.reaper import (
    N_SAVED_DEFAULT, reaper_pass, reaper_from_latent,
)


# ── worked example ──────────────────────────────────────────────────────
def test_reaper_worked_example():
    """40 channels, N_saved = 36 -> 36 Henad, 4 Nexus, fraction 0.10."""
    henad_values, henad_idx, nexus_idx, fraction = reaper_pass(
        np.ones(40), n_saved=N_SAVED_DEFAULT)
    assert henad_idx.size == 36
    assert nexus_idx.size == 4
    assert np.isclose(fraction, 4.0 / 40.0)
    assert np.count_nonzero(henad_values) == 36
    assert np.all(henad_values[nexus_idx] == 0)


# ── under / at capacity ─────────────────────────────────────────────────
def test_reaper_empty_input():
    hv, hi, ni, f = reaper_pass(np.array([], dtype=np.float64), n_saved=36)
    assert hv.size == 0
    assert hi.size == 0
    assert ni.size == 0
    assert f == 0.0


def test_reaper_under_capacity_no_nexus():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    hv, hi, ni, f = reaper_pass(x, n_saved=36)
    assert np.array_equal(hv, x)
    assert hi.size == 5
    assert ni.size == 0
    assert f == 0.0


def test_reaper_at_capacity_no_nexus():
    x = np.ones(36)
    hv, hi, ni, f = reaper_pass(x, n_saved=36)
    assert np.array_equal(hv, x)
    assert ni.size == 0
    assert f == 0.0


# ── top-k selection ─────────────────────────────────────────────────────
def test_reaper_keeps_top_by_magnitude():
    x = np.array([1.0, 5.0, 2.0, 8.0, 3.0, 7.0])
    hv, hi, ni, _ = reaper_pass(x, n_saved=2)
    assert set(hi.tolist()) == {3, 5}
    assert set(ni.tolist()) == {0, 1, 2, 4}
    assert np.all(hv[ni] == 0)


def test_reaper_zero_capacity_removes_all():
    x = np.array([1.0, 2.0, 3.0])
    hv, hi, ni, f = reaper_pass(x, n_saved=0)
    assert hi.size == 0
    assert ni.size == 3
    assert np.all(hv == 0)
    assert np.isclose(f, 1.0)


def test_reaper_deterministic_on_ties():
    x = np.ones(10)
    a = reaper_pass(x, n_saved=5)
    b = reaper_pass(x, n_saved=5)
    assert np.array_equal(a[1], b[1])
    assert np.array_equal(a[2], b[2])


# ── weights override ranking ────────────────────────────────────────────
def test_reaper_weights_override_ranking():
    x = np.array([10.0, 1.0, 1.0, 1.0])
    w = np.array([0.1, 10.0, 10.0, 10.0])
    hv, hi, ni, f = reaper_pass(x, n_saved=3, weights=w)
    assert set(hi.tolist()) == {1, 2, 3}
    assert set(ni.tolist()) == {0}
    # Nexus fraction measured on x, not weights.
    assert np.isclose(f, 10.0 / 13.0)


# ── validation ──────────────────────────────────────────────────────────
def test_reaper_rejects_non_1d():
    with pytest.raises(ValueError, match="1D"):
        reaper_pass(np.zeros((3, 3)), n_saved=2)


def test_reaper_rejects_negative_values():
    with pytest.raises(ValueError, match="non-negative"):
        reaper_pass(np.array([1.0, -1.0]), n_saved=1)


def test_reaper_rejects_negative_capacity():
    with pytest.raises(ValueError, match="n_saved"):
        reaper_pass(np.array([1.0]), n_saved=-1)


def test_reaper_rejects_weight_shape_mismatch():
    with pytest.raises(ValueError, match="weights shape"):
        reaper_pass(np.ones(3), n_saved=2, weights=np.ones(4))


# ── bridge from latent packet ───────────────────────────────────────────
def test_reaper_from_latent_bridge():
    from resileos.core import CoreConfig, ResidualCore
    core = ResidualCore(CoreConfig(m=16, n=16, r=12), seed=0)
    W = np.random.default_rng(0).standard_normal((16, 16))
    packet = core.step(W)
    hv, hi, ni, f = reaper_from_latent(packet, n_saved=8)
    assert hi.size + ni.size == 12
    assert hi.size <= 8
    assert 0.0 <= f <= 1.0
