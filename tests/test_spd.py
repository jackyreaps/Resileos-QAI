"""Tests for the SPD precondition utility (RES-601 §7 item 3)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.spd import (
    assert_spd, is_spd, min_eigenvalue, isotropic_metric,
)


# ── assert_spd / is_spd ─────────────────────────────────────────────────
def test_identity_is_spd():
    assert is_spd(np.eye(4))
    assert_spd(np.eye(4))


def test_positive_diagonal_is_spd():
    M = np.diag([1.0, 2.0, 3.0])
    assert is_spd(M)
    assert_spd(M)


def test_zero_diagonal_not_spd():
    M = np.diag([1.0, 0.0, 3.0])
    assert not is_spd(M)
    with pytest.raises(ValueError, match="not positive-definite"):
        assert_spd(M)


def test_negative_diagonal_not_spd():
    M = np.diag([1.0, -1.0, 3.0])
    assert not is_spd(M)


def test_nonsymmetric_rejected():
    M = np.array([[1.0, 2.0], [0.0, 1.0]])
    assert not is_spd(M)
    with pytest.raises(ValueError, match="not symmetric"):
        assert_spd(M)


def test_batched_spd():
    B = np.tile(np.eye(3), (5, 1, 1))
    assert is_spd(B)
    assert_spd(B)


def test_batched_with_one_bad_rejected():
    B = np.tile(np.eye(3), (5, 1, 1)).copy()
    B[2] = np.diag([1.0, -1.0, 1.0])
    assert not is_spd(B)


def test_rank_deficient_rejected():
    v = np.array([1.0, 2.0, 3.0])
    M = np.outer(v, v)
    assert not is_spd(M)


def test_tolerance_loosens_acceptance():
    M = np.diag([1.0, 1e-12])
    assert not is_spd(M, tol=1e-10)
    assert is_spd(M, tol=1e-14)


def test_assert_spd_raises_on_wrong_shape():
    with pytest.raises(ValueError, match=r"\[D, D\]|\[B, D, D\]"):
        assert_spd(np.random.randn(3))


def test_assert_spd_raises_on_nonsquare():
    with pytest.raises(ValueError, match="not square"):
        assert_spd(np.random.randn(3, 4))


# ── min_eigenvalue ──────────────────────────────────────────────────────
def test_min_eigenvalue_simple():
    M = np.diag([2.0, 3.0, 5.0])
    assert min_eigenvalue(M) == pytest.approx(2.0, abs=1e-9)


def test_min_eigenvalue_nonsquare_raises():
    with pytest.raises(ValueError, match="not square"):
        min_eigenvalue(np.random.randn(3, 4))


# ── isotropic_metric ────────────────────────────────────────────────────
def test_isotropic_metric_shape_and_dtype():
    M = isotropic_metric(8, re_eps=0.0)
    assert M.shape == (8, 8)
    assert M.dtype == np.float64


def test_isotropic_metric_default_identity():
    M = isotropic_metric(4, re_eps=0.0)
    assert np.allclose(M, np.eye(4))


def test_isotropic_metric_scales_with_re_eps():
    M = isotropic_metric(4, re_eps=1.0)
    assert np.allclose(M, 0.5 * np.eye(4))


def test_isotropic_metric_rejects_re_eps_at_minus_one():
    with pytest.raises(ValueError, match="Re_ε must be"):
        isotropic_metric(4, re_eps=-1.0)


def test_isotropic_metric_is_spd():
    M = isotropic_metric(8, re_eps=0.5)
    assert is_spd(M)
