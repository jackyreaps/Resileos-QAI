"""Tests for the directional diagnostic (RES-308 / RES-300)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import CoreConfig, ResidualCore
from resileos.directional import (
    DirectionalHDRIFT, embed_block, evaluate_modes, _unit, _tangent,
)


DIM = 64
M = 8
N = 8
R = 4


def _block(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    U = rng.standard_normal((M, 4))
    V = rng.standard_normal((4, N))
    return (U @ V + 0.05 * rng.standard_normal((M, N))).astype(np.float64)


def _packet(seed: int = 0):
    core = ResidualCore(CoreConfig(m=M, n=N, r=R), seed=seed)
    return core.step(_block(seed))


# ── helpers ─────────────────────────────────────────────────────────────
def test_unit_norm():
    v = np.array([3.0, 4.0, 0.0, 0.0])
    assert np.isclose(np.linalg.norm(_unit(v)), 1.0)


def test_unit_of_zero():
    assert np.allclose(_unit(np.zeros(4)), np.zeros(4))


def test_tangent_removes_radial():
    x = np.array([1.0, 0.0, 0.0])
    d = np.array([2.0, 1.0, 0.0])
    t = _tangent(d, x)
    assert np.isclose(np.dot(t, x), 0.0)
    assert np.isclose(t[1], 1.0)


def test_embed_block_pads():
    W = np.ones((3, 3))
    out = embed_block(W, 20)
    assert out.shape == (20,)
    assert np.sum(out[:9]) == 9.0
    assert np.sum(out[9:]) == 0.0


# ── DirectionalHDRIFT construction ──────────────────────────────────────
def test_constructor_rejects_bad_mode():
    with pytest.raises(ValueError, match="mode"):
        DirectionalHDRIFT(DIM, M, N, r=R, mode="nonsense")


def test_constructor_rejects_bad_weight():
    with pytest.raises(ValueError, match="hybrid_trend_weight"):
        DirectionalHDRIFT(DIM, M, N, r=R, hybrid_trend_weight=1.5)


def test_constructor_rejects_bad_window():
    with pytest.raises(ValueError, match="trend_window"):
        DirectionalHDRIFT(DIM, M, N, r=R, trend_window=0)


# ── step outputs ────────────────────────────────────────────────────────
def test_reconstruction_step_is_tautology():
    model = DirectionalHDRIFT(DIM, M, N, r=R, mode="reconstruction")
    packet = _packet()
    x = _unit(embed_block(_block(), DIM))
    out = model.step(x, packet)
    assert np.allclose(out["y"], out["target"])
    assert out["err_after"] < 1e-9
    assert out["label"] == "reconstruction_tautology"


def test_trend_step_first_call_is_zero_change():
    """First step has no history, so trend is zero; y == x."""
    model = DirectionalHDRIFT(DIM, M, N, r=R, mode="trend")
    packet = _packet()
    x = _unit(embed_block(_block(), DIM))
    out = model.step(x, packet)
    assert np.allclose(out["y"], x)


def test_trend_step_produces_unit_output():
    model = DirectionalHDRIFT(DIM, M, N, r=R, mode="trend")
    core = ResidualCore(CoreConfig(m=M, n=N, r=R), seed=0)
    x = _unit(embed_block(_block(), DIM))
    for i in range(4):
        packet = core.step(_block(i))
        out = model.step(x, packet)
        x = out["y"]
        assert np.isclose(np.linalg.norm(x), 1.0, atol=1e-9)


def test_multi_trend_step_produces_unit_output():
    model = DirectionalHDRIFT(DIM, M, N, r=R, mode="multi_trend",
                              trend_window=3)
    core = ResidualCore(CoreConfig(m=M, n=N, r=R), seed=0)
    x = _unit(embed_block(_block(), DIM))
    for i in range(6):
        packet = core.step(_block(i))
        out = model.step(x, packet)
        x = out["y"]
        assert np.isclose(np.linalg.norm(x), 1.0, atol=1e-9)


def test_hybrid_weight_zero_equals_reconstruction():
    model = DirectionalHDRIFT(DIM, M, N, r=R, mode="hybrid",
                              hybrid_trend_weight=0.0)
    packet = _packet()
    x = _unit(embed_block(_block(), DIM))
    out = model.step(x, packet)
    assert np.allclose(out["y"], out["target"])
    assert out["label"] == "reconstruction_tautology"


def test_hybrid_label():
    model = DirectionalHDRIFT(DIM, M, N, r=R, mode="hybrid",
                              hybrid_trend_weight=0.5)
    packet = _packet()
    x = _unit(embed_block(_block(), DIM))
    out = model.step(x, packet)
    assert out["label"] == "hybrid"


# ── evaluate_modes ──────────────────────────────────────────────────────
def test_evaluate_modes_shape():
    blocks = [_block(i) for i in range(4)]
    report = evaluate_modes(blocks, r=R, horizon=3,
                            trend_weights=(0.0, 0.5, 1.0),
                            trend_window=2)
    assert "reconstruction" in report
    assert "trend" in report
    assert "multi_trend" in report
    assert "hybrid" in report
    assert "weight_0" in report["hybrid"]
    assert "weight_0.5" in report["hybrid"]
    assert "weight_1" in report["hybrid"]


def test_reconstruction_reaches_full_reduction():
    blocks = [_block(i) for i in range(3)]
    report = evaluate_modes(blocks, r=R, horizon=3,
                            trend_weights=(0.0,))
    assert report["reconstruction"]["reduction_pct"] > 99.0


def test_hybrid_weight_zero_matches_reconstruction():
    blocks = [_block(i) for i in range(3)]
    report = evaluate_modes(blocks, r=R, horizon=3,
                            trend_weights=(0.0,))
    rec = report["reconstruction"]["reduction_pct"]
    hyb0 = report["hybrid"]["weight_0"]["reduction_pct"]
    assert np.isclose(rec, hyb0, atol=1e-6)


def test_hybrid_dilutes_reconstruction_at_high_weight():
    blocks = [_block(i) for i in range(3)]
    report = evaluate_modes(blocks, r=R, horizon=3,
                            trend_weights=(0.0, 1.0))
    hyb0 = report["hybrid"]["weight_0"]["reduction_pct"]
    hyb1 = report["hybrid"]["weight_1"]["reduction_pct"]
    # At w=1 the trend dilutes the reconstruction pull.
    assert hyb1 < hyb0
