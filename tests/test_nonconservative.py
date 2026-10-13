"""Tests for the non-conservative extension to the residual core."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import ResidualCore, CoreConfig
from resileos.substrate.nonconservative import NonConservativeOperator


# ── operator unit tests ───────────────────────────────────────────────
def test_conservative_mode_is_identity():
    op = NonConservativeOperator(r=4, mode="conservative")
    op.update(F_res=10.0, DeltaS=5.0, mu=1)
    assert np.allclose(op.diagonal(), 1.0 + 0.0j)


def test_det_one_constraint():
    op = NonConservativeOperator(r=6, mode="non-conservative")
    for _ in range(50):
        op.update(F_res=0.5, DeltaS=0.3, mu=1)
    D = op.diagonal()
    prod = np.prod(D)
    assert np.isclose(abs(prod), 1.0, atol=1e-9)


def test_sum_g_zero():
    op = NonConservativeOperator(r=6, mode="non-conservative")
    for _ in range(50):
        op.update(F_res=0.5, DeltaS=0.3, mu=1)
    assert np.isclose(np.sum(op.g), 0.0, atol=1e-12)


def test_sum_theta_zero():
    op = NonConservativeOperator(r=6, mode="non-conservative")
    for _ in range(50):
        op.update(F_res=0.5, DeltaS=0.3, mu=0)
    assert np.isclose(np.sum(op.theta), 0.0, atol=1e-12)


def test_anisotropy_grows_with_drive():
    op = NonConservativeOperator(r=8, mode="non-conservative")
    op.update(F_res=0.0, DeltaS=0.0, mu=0)
    a0 = op.anisotropy()
    for _ in range(30):
        op.update(F_res=2.0, DeltaS=1.5, mu=1)
    a1 = op.anisotropy()
    assert a1 > a0


def test_anisotropy_bounded_by_gamma_max():
    op = NonConservativeOperator(r=8, mode="non-conservative", gamma_max=0.3)
    for _ in range(200):
        op.update(F_res=100.0, DeltaS=100.0, mu=1)
    assert op.anisotropy() < np.exp(2 * 0.3) + 1e-6


def test_effective_matrix_det_one():
    op = NonConservativeOperator(r=4, mode="non-conservative")
    for _ in range(20):
        op.update(F_res=1.0, DeltaS=0.5, mu=1)
    Lambda = np.eye(4, dtype=np.complex128) * 0.5
    J = op.effective_matrix(Lambda)
    assert np.isclose(abs(np.linalg.det(J)), 1.0, atol=1e-9)


# ── core integration tests ────────────────────────────────────────────
def _cfg():
    return CoreConfig(m=16, n=16, r=4)


def _W(seed):
    return np.random.default_rng(seed).standard_normal((16, 16))


def test_core_conservative_mode_is_det_one():
    core = ResidualCore(_cfg(), seed=0, non_conservative=False)
    for i in range(10):
        p = core.step(_W(i), F_res=0.1 * i, DeltaS=0.5, mu=i % 2)
        assert p.volume_ok
        assert np.allclose(np.abs(p.D), 1.0, atol=1e-9)


def test_core_non_conservative_mode_det_one():
    core = ResidualCore(_cfg(), seed=0, non_conservative=True)
    for i in range(20):
        p = core.step(_W(i), F_res=0.5, DeltaS=0.3, mu=i % 2)
        assert p.volume_ok, f"volume check failed at step {i}"
        prod = np.prod(p.D)
        assert np.isclose(abs(prod), 1.0, atol=1e-8)


def test_core_non_conservative_anisotropy_evolves():
    """Basin should reorganize: |d_i| spread should grow with drive."""
    core = ResidualCore(_cfg(), seed=0, non_conservative=True)
    core.step(_W(0), F_res=0.0, DeltaS=0.0, mu=0)   # warm up
    a_start = np.abs(core.D).max() / np.abs(core.D).min()
    for i in range(30):
        core.step(_W(i), F_res=2.0, DeltaS=1.0, mu=1)
    a_end = np.abs(core.D).max() / np.abs(core.D).min()
    assert a_end > a_start + 0.01


def test_core_conservative_anisotropy_stays_one():
    core = ResidualCore(_cfg(), seed=0, non_conservative=False)
    for i in range(20):
        core.step(_W(i), F_res=2.0, DeltaS=1.0, mu=1)
    a = np.abs(core.D).max() / np.abs(core.D).min()
    assert np.isclose(a, 1.0, atol=1e-9)


def test_packet_hash_deterministic_with_non_conservative():
    from resileos.packet import packet_hash
    core1 = ResidualCore(_cfg(), seed=0, non_conservative=True)
    core2 = ResidualCore(_cfg(), seed=0, non_conservative=True)
    p1 = core1.step(_W(0), F_res=0.5, DeltaS=0.3, mu=1)
    p2 = core2.step(_W(0), F_res=0.5, DeltaS=0.3, mu=1)
    assert packet_hash(p1) == packet_hash(p2)


def test_packet_hash_changes_with_different_drive():
    """D is part of the hash; different drive → different hash."""
    from resileos.packet import packet_hash
    core1 = ResidualCore(_cfg(), seed=0, non_conservative=True)
    core2 = ResidualCore(_cfg(), seed=0, non_conservative=True)
    for i in range(5):
        core1.step(_W(i), F_res=0.1, DeltaS=0.2, mu=0)
    for i in range(5):
        core2.step(_W(i), F_res=2.0, DeltaS=1.0, mu=1)
    p1 = core1.step(_W(99), F_res=0.1, DeltaS=0.2, mu=0)
    p2 = core2.step(_W(99), F_res=2.0, DeltaS=1.0, mu=1)
    assert packet_hash(p1) != packet_hash(p2)


def test_factors_kwarg_still_works():
    """External factors (used by training) still work with the extension."""
    core = ResidualCore(_cfg(), seed=0, non_conservative=True)
    Ub = np.sign(np.random.default_rng(1).standard_normal((16, 4))).astype(np.float32)
    Vb = np.sign(np.random.default_rng(2).standard_normal((4, 16))).astype(np.float32)
    p = core.step(_W(0), F_res=0.5, DeltaS=0.3, mu=1, factors=(Ub, Vb))
    assert p.volume_ok
    assert np.allclose(p.Ub, Ub)
    assert np.allclose(p.Vb, Vb)
