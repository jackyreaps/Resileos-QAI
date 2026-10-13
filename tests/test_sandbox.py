"""Tests for the Causal Sandbox Index (RES-305)."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.sandbox import (
    volume_residual,
    internal_prediction_error,
    compute_csi,
    CSIState,
    fast_confidence,
)


# ── volume residual ─────────────────────────────────────────────────────
def test_volume_residual_zero_for_unit_det():
    assert volume_residual(1.0) == 0.0
    assert volume_residual(-1.0) == 0.0


def test_volume_residual_grows_with_drift():
    r1 = volume_residual(1.5)
    r2 = volume_residual(5.0)
    assert r1 > 0.0
    assert r2 > r1


def test_volume_residual_infinite_for_zero_det():
    assert math.isinf(volume_residual(0.0))


# ── internal prediction error ───────────────────────────────────────────
def test_internal_error_zero_when_equal():
    e = internal_prediction_error([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert e == 0.0


def test_internal_error_positive_when_different():
    e = internal_prediction_error([1.0, 2.0, 3.0], [1.1, 2.0, 3.0])
    assert e > 0.0


def test_internal_error_normalized():
    # A large-magnitude state with a small absolute change should give a
    # smaller normalized error than a small-magnitude state with the
    # same absolute change.
    e_big = internal_prediction_error([100.0], [99.9])
    e_small = internal_prediction_error([1.0], [0.9])
    assert e_big < e_small


def test_internal_error_shape_check():
    with pytest.raises(ValueError):
        internal_prediction_error([1.0, 2.0], [1.0])


# ── CSI trajectory values ───────────────────────────────────────────────
def test_csi_perfect_trajectory():
    csi = compute_csi([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    assert math.isclose(csi, 1.0, abs_tol=1e-12)


def test_csi_empty_trajectory_returns_one():
    assert compute_csi([], []) == 1.0


def test_csi_drops_with_volume_leak():
    csi = compute_csi([0.5, 0.5, 0.5], [0.0, 0.0, 0.0])
    assert 0.0 < csi < 1.0
    assert math.isclose(csi, math.exp(-0.5), rel_tol=1e-9)


def test_csi_drops_with_internal_error():
    csi = compute_csi([0.0, 0.0, 0.0], [0.5, 0.5, 0.5])
    assert 0.0 < csi < 1.0
    assert math.isclose(csi, math.exp(-0.5), rel_tol=1e-9)


def test_csi_drops_multiplicatively():
    csi_v = compute_csi([0.5] * 3, [0.0] * 3)
    csi_e = compute_csi([0.0] * 3, [0.5] * 3)
    csi_both = compute_csi([0.5] * 3, [0.5] * 3)
    assert math.isclose(csi_both, csi_v * csi_e, rel_tol=1e-9)


def test_csi_with_external_term():
    csi = compute_csi([0.0] * 3, [0.0] * 3, external_errors=[1.0, 1.0, 1.0])
    assert math.isclose(csi, 0.5, rel_tol=1e-9)


def test_csi_without_external_term():
    csi = compute_csi([0.0] * 3, [0.0] * 3, external_errors=[1.0, 1.0, 1.0],
                      external_term=False)
    assert math.isclose(csi, 1.0, abs_tol=1e-12)


def test_csi_nonfinite_returns_zero():
    csi = compute_csi([float("inf")], [0.0])
    assert csi == 0.0


# ── living-system factor ────────────────────────────────────────────────
def test_living_factor_penalizes_frozen_systems():
    csi_frozen = compute_csi([0.0] * 10, [0.0] * 10, living_factor=True,
                             optimal_drift=0.1)
    csi_moderate = compute_csi([0.0] * 10, [0.1] * 10, living_factor=True,
                               optimal_drift=0.1)
    assert csi_moderate > csi_frozen


def test_living_factor_at_optimal_drift_is_one():
    csi = compute_csi([0.0], [0.1], living_factor=True, optimal_drift=0.1)
    assert math.isclose(csi, 1.0, abs_tol=1e-9)


# ── CSIState ────────────────────────────────────────────────────────────
def test_state_empty_returns_one():
    s = CSIState(window=8)
    assert s.value() == 1.0
    assert s.samples() == 0


def test_state_accumulates():
    s = CSIState(window=4)
    for _ in range(3):
        s.update(0.1, 0.2)
    assert s.samples() == 3
    assert 0.0 < s.value() < 1.0


def test_state_window_drops_old():
    s = CSIState(window=2)
    s.update(10.0, 0.0)
    s.update(0.0, 0.0)
    v_before = s.value()
    s.update(0.0, 0.0)
    v_after = s.value()
    assert v_after > v_before


def test_state_persistence_roundtrip():
    s1 = CSIState(window=4)
    s1.update(0.1, 0.2)
    s1.update(0.3, 0.4)
    d = s1.state_dict()
    s2 = CSIState(window=4)
    s2.load_state_dict(d)
    assert s2.samples() == s1.samples()
    assert math.isclose(s2.value(), s1.value(), rel_tol=1e-9)


# ── fast confidence ─────────────────────────────────────────────────────
def test_fast_confidence_bounded():
    for c in (0.0, 0.5, 5.0):
        for s in (0.0, 0.05, 1.0):
            for csi in (0.0, 0.5, 1.0):
                fc = fast_confidence(c, s, csi)
                assert 0.0 <= fc <= 1.0


def test_fast_confidence_zero_when_csi_zero():
    assert fast_confidence(10.0, 0.1, 0.0) == 0.0


def test_fast_confidence_scales_with_csi():
    a = fast_confidence(1.0, 0.1, 0.3)
    b = fast_confidence(1.0, 0.1, 0.9)
    assert b > a


def test_fast_confidence_no_stored_items():
    assert math.isclose(fast_confidence(0.5, 0.0, 0.8), 0.8, rel_tol=1e-9)
    assert fast_confidence(0.0, 0.0, 0.8) == 0.0
