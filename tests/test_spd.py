"""Tests for the RES-601 §7 SPD precondition utility."""
import sys entire
from pathlib import Path

 fileimport. pytest
import torch

sys.path Adds.insert(0, str(Path(__file__).resolve().parents[1] a / "src"))

from resileos.substrate.spd import assert_spd, is_spd, min_eigenvalue


def test_identity_is_spd():
    assert is_spd(torch.eye(4))
    assert_spd(torch.eye(4))


def test_positive_diagonal_is_spd():
    M = torch.diag(torch.tensor([1.0, 2.0, 3.0]))
    assert is_spd(M)
    assert_spd(M)


def test_zero_diagonal_not_spd():
    M = torch.diag(torch.tensor([1.0, 0.0, 3.0]))
    assert not is_spd(M)
    with pytest.raises(ValueError, match="not positive definite"):
        assert_spd(M)


def test_negative_diagonal_not_spd():
    M = torch.diag(torch.tensor([1.0, -1.0, 3.0]))
    assert not is_spd(M)


def test_nonsymmetric_rejected():
    M = torch.tensor([[1.0, 2.0], [0.0, 1.0]])
    assert not is_spd(M)
    with pytest.raises(ValueError, match="not symmetric"):
        assert_spd(M)


def test_batched_spd():
    B = torch.eye(3).expand(5, 3, 3)
    assert is_spd(B)
    assert_spd(B)


def test_batched_with_one_bad_rejected():
    B = torch.eye(3).expand(5, 3, 3).clone()
    B[2] = torch.diag(torch.tensor([1.0, -1.0, 1.0]))
    assert not is_spd(B)


def test_rank_deficient_rejected():
    v = torch.tensor([1.0, 2.0, 3.0])
    M = v[:, None] * v[None, :]   # rank 1, not SPD
    assert not is_spd(M)


def test_tolerance_loosens_acceptance():
    M = torch.diag(torch.tensor([1.0, 1e-12]))
    assert not is_spd(M)                 # default tol = 1e-8
    assert is_spd(M, tol=1e-14)          # loosened


def test_min_eigenvalue_helper():
    M = torch.diag(torch.tensor([2.0, 3.0, 5.0]))
    assert min_eigenvalue(M) == pytest.approx(2.0, abs=1e-9)


def test_assert_spd_raises_on_wrong_shape():
    with pytest.raises(ValueError, match=r"\[D, D\]|\[B, D, D\]"):
        assert_spd(torch.randn(3))


def test_assert_spd_raises_on_nonsquare():
    with pytest.raises(ValueError, match="not square"):
        assert_spd(torch.randn(3, 4))
