"""Tests for φ-compression."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import CoreConfig
from resileos.phi_compress import (
    PHI_HAT,
    contract_rank, contract_depth, contract_repeated,
    zeckendorf_rank, select_by_zeckendorf,
    contracted_ladder, contract_config,
)
from resileos.substrate.oscillator import PHI, golden_ladder


# ── constants ───────────────────────────────────────────────────────────
def test_phi_hat_is_phi_minus_one():
    assert np.isclose(PHI_HAT, 1.0 / PHI)
    assert np.isclose(PHI_HAT, PHI - 1.0)


# ── worked examples ─────────────────────────────────────────────────────
def test_contract_rank_worked_examples():
    assert contract_rank(8) == 4
    assert contract_rank(16) == 9
    assert contract_rank(64) == 39


def test_contract_depth_worked_example():
    assert contract_depth(64) == 39


# ── clamping ────────────────────────────────────────────────────────────
def test_contract_rank_clamps_to_min():
    assert contract_rank(1) == 1
    assert contract_rank(0) == 1
    assert contract_rank(0, min_rank=3) == 3


def test_contract_rank_rejects_negative():
    with pytest.raises(ValueError, match="r must be"):
        contract_rank(-1)


def test_contract_rank_rejects_bad_min():
    with pytest.raises(ValueError, match="min_rank"):
        contract_rank(8, min_rank=0)


# ── repeated ────────────────────────────────────────────────────────────
def test_contract_repeated_three_steps():
    """64 -> 39 -> 24 -> 14."""
    assert contract_repeated(64, steps=3) == 14


def test_contract_repeated_stops_at_min():
    assert contract_repeated(64, steps=100, min_value=4) >= 4


def test_contract_repeated_zero_steps():
    assert contract_repeated(8, steps=0) == 8


def test_contract_repeated_rejects_negative_steps():
    with pytest.raises(ValueError, match="steps"):
        contract_repeated(8, steps=-1)


# ── zeckendorf_rank ─────────────────────────────────────────────────────
def test_zeckendorf_zero():
    assert zeckendorf_rank(0) == 0


def test_zeckendorf_fibonacci_terms():
    for n in (1, 2, 3, 5, 8, 13):
        assert zeckendorf_rank(n) == 1, f"zeckendorf_rank({n}) should be 1"


def test_zeckendorf_small_values():
    assert zeckendorf_rank(4) == 2   # 3 + 1
    assert zeckendorf_rank(6) == 2   # 5 + 1
    assert zeckendorf_rank(7) == 2   # 5 + 2
    assert zeckendorf_rank(12) == 3  # 8 + 3 + 1


# ── select_by_zeckendorf ────────────────────────────────────────────────
def test_select_returns_keep_indices():
    idx = select_by_zeckendorf(20, keep=5)
    assert idx.shape == (5,)
    assert len(set(idx.tolist())) == 5


def test_select_keep_all():
    idx = select_by_zeckendorf(10, keep=10)
    assert set(idx.tolist()) == set(range(10))


def test_select_keep_zero():
    idx = select_by_zeckendorf(10, keep=0)
    assert idx.size == 0


def test_select_rejects_bad_keep():
    with pytest.raises(ValueError, match="keep"):
        select_by_zeckendorf(5, keep=6)


def test_select_rejects_zero_n():
    with pytest.raises(ValueError, match="n must be"):
        select_by_zeckendorf(0, keep=0)


# ── contracted_ladder ───────────────────────────────────────────────────
def test_contracted_ladder_is_prefix():
    full = golden_ladder(8)
    contracted = contracted_ladder(8)
    assert contracted.shape == (4,)
    assert np.allclose(contracted, full[:4])


def test_contracted_ladder_preserves_irrationality():
    """No pair of contracted ladder entries forms a low-order rational."""
    omega = contracted_ladder(8)
    for i in range(len(omega)):
        for j in range(i + 1, len(omega)):
            ratio = omega[i] / (omega[j] + 1e-12)
            for m in (2, 3, 5, 7):
                assert not np.isclose(ratio * m, round(ratio * m), atol=1e-9)


# ── contract_config ─────────────────────────────────────────────────────
def test_contract_config_returns_new_coreconfig():
    cfg = CoreConfig(m=16, n=16, r=8)
    cfg2 = contract_config(cfg)
    assert cfg2.r == 4
    assert cfg2.m == cfg.m
    assert cfg2.n == cfg.n
    assert cfg.r == 8  # original unchanged


def test_contract_config_preserves_other_fields():
    cfg = CoreConfig(m=32, n=32, r=16, alpha=0.9, beta=0.1, gamma=0.05,
                     n_residual_layers=8)
    cfg2 = contract_config(cfg)
    assert cfg2.alpha == 0.9
    assert cfg2.beta == 0.1
    assert cfg2.gamma == 0.05
    assert cfg2.n_residual_layers == 8


# ── volume guard still passes at contracted rank ────────────────────────
def test_volume_guard_passes_at_contracted_rank():
    from resileos.core import ResidualCore
    r_new = contract_rank(12)
    core = ResidualCore(
        CoreConfig(m=16, n=16, r=r_new), seed=0, non_conservative=True)
    W = np.random.default_rng(0).standard_normal((16, 16))
    p = core.step(W, mu=1, F_res=0.5, DeltaS=0.5)
    assert p.volume_ok
    assert abs(np.log10(abs(p.volume) + 1e-300)) < 1e-9
