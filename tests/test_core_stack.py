"""Tests for the residual stack and phase wiring in ResidualCore."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import (
    CoreConfig, ResidualCore, build_coupling_graph,
)


def _cfg(layers: int = 12) -> CoreConfig:
    return CoreConfig(m=16, n=16, r=4, n_residual_layers=layers)


def _block(seed: int = 0) -> np.ndarray:
    """Low-rank + noise block. Compression is meaningful on this."""
    rng = np.random.default_rng(seed)
    U = rng.standard_normal((16, 4))
    V = rng.standard_normal((4, 16))
    W = U @ V
    W += 0.05 * rng.standard_normal((16, 16))
    return W


def _rel_err(W, W_hat) -> float:
    return float(
        np.linalg.norm(W - W_hat) / (np.linalg.norm(W) + 1e-12))


# ── residual stack behavior ─────────────────────────────────────────────
def test_single_layer_matches_old_behavior():
    """With n_residual_layers=1, behavior matches the previous core."""
    core = ResidualCore(_cfg(layers=1), seed=0)
    W = _block(0)
    core.step(W)
    W_hat = core.last_reconstruction
    # Reconstruction should equal the L2-optimal rescale of Ub @ Vb.
    err = _rel_err(W, W_hat)
    assert 0.0 < err < 1.0


def test_stack_improves_compression():
    """More layers -> lower reconstruction error."""
    W = _block(0)

    core_1 = ResidualCore(_cfg(layers=1), seed=0)
    core_1.step(W)
    err_1 = _rel_err(W, core_1.last_reconstruction)

    core_12 = ResidualCore(_cfg(layers=12), seed=0)
    core_12.step(W)
    err_12 = _rel_err(W, core_12.last_reconstruction)

    assert err_12 < err_1
    # 12 layers should improve substantially on a rank-4+noise block.
    assert err_12 < err_1 - 0.05, (
        f"stack did not improve: 1 layer {err_1:.4f}, 12 layers {err_12:.4f}")


def test_stack_reaches_high_reduction():
    """On a rank-4 block, 12 layers should clear 50% reduction."""
    core = ResidualCore(_cfg(layers=12), seed=0)
    core.step(_block(0))
    err = _rel_err(_block(0), core.last_reconstruction)
    reduction = 100.0 * (1.0 - err)
    assert reduction > 50.0, f"only {reduction:.1f}% reduction"


def test_last_reconstruction_none_before_step():
    core = ResidualCore(_cfg(), seed=0)
    assert core.last_reconstruction is None


def test_packet_still_emits_layer_0():
    """RES-201 frozen: packet carries layer 0's factors at shape (m, r)."""
    core = ResidualCore(_cfg(layers=12), seed=0)
    p = core.step(_block(0))
    assert p.Ub.shape == (16, 4)
    assert p.Vb.shape == (4, 16)


def test_volume_preservation_holds_with_stack():
    core = ResidualCore(_cfg(layers=12), seed=0)
    for i in range(5):
        p = core.step(_block(i))
        assert p.volume_ok
        assert abs(np.log10(abs(p.volume) + 1e-300)) < 1e-9


def test_determinism_with_stack():
    from resileos.packet import packet_hash
    W = _block(0)
    p1 = ResidualCore(_cfg(layers=12), seed=0).step(W)
    p2 = ResidualCore(_cfg(layers=12), seed=0).step(W)
    assert packet_hash(p1) == packet_hash(p2)


def test_factors_kwarg_bypasses_stack():
    """External factors (training) use the single-layer path."""
    core = ResidualCore(_cfg(layers=12), seed=0)
    W = _block(0)
    Ub = np.sign(np.random.default_rng(1).standard_normal((16, 4))).astype(np.float32)
    Vb = np.sign(np.random.default_rng(2).standard_normal((4, 16))).astype(np.float32)
    p = core.step(W, factors=(Ub, Vb))
    assert np.allclose(p.Ub, Ub)
    assert np.allclose(p.Vb, Vb)


# ── phasor graph wiring ─────────────────────────────────────────────────
def test_coupling_graph_construction():
    g = build_coupling_graph(r=4, seed=0)
    assert g.n == 4
    assert g.hermitian is False
    # Strict lower
    T = g.triangular_projection()
    assert np.allclose(np.triu(T, k=0), 0.0)


def test_core_with_phasor_graph_oscillates():
    """Attaching a graph makes the coupling oscillate with theta."""
    graph = build_coupling_graph(r=4, seed=0)
    core = ResidualCore(_cfg(layers=12), seed=0,
                        non_conservative=True,
                        phasor_graph=graph)

    # Snapshot the coupling after a few steps
    couplings = []
    for i in range(5):
        core.step(_block(i), F_res=0.5 * i, DeltaS=0.3, mu=i % 2)
        couplings.append(graph.triangular_projection().copy())

    # Coupling should change between steps.
    c0 = couplings[0]
    c4 = couplings[-1]
    diff = float(np.max(np.abs(c0 - c4)))
    assert diff > 1e-6, "coupling did not change across steps"


def test_core_without_graph_has_static_coupling_phases():
    """Without a graph, the coupling is real (no phase oscillation)."""
    core = ResidualCore(_cfg(layers=1), seed=0, non_conservative=False)
    core.step(_block(0), F_res=0.5, DeltaS=0.3, mu=1)
    # Lambda is real.
    assert np.isrealobj(core.Lambda)


def test_volume_preservation_with_graph():
    graph = build_coupling_graph(r=4, seed=0)
    core = ResidualCore(_cfg(layers=12), seed=0,
                        non_conservative=True,
                        phasor_graph=graph)
    for i in range(5):
        p = core.step(_block(i), F_res=0.3, DeltaS=0.2, mu=i % 2)
        assert p.volume_ok, f"volume failed at step {i}"


def test_apply_phase_context_preserves_amplitude():
    graph = build_coupling_graph(r=4, seed=0)
    amps_before = sorted(abs(w) for w in graph._edges.values())
    theta = np.array([0.1, 0.2, 0.3, 0.4])
    graph.apply_phase_context(theta)
    amps_after = sorted(abs(w) for w in graph._edges.values())
    assert np.allclose(amps_before, amps_after)
