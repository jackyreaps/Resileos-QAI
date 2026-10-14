"""Tests for the substrate carrier (RES-300 / RES-201 boundary)."""
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import CoreConfig, ResidualCore
from resileos.carrier import (
    SubstrateCarrier, pack_packet, packet_feature_dim,
)


M, N, R = 8, 8, 4


def _packet(seed: int = 0):
    core = ResidualCore(CoreConfig(m=M, n=N, r=R), seed=seed)
    W = np.random.default_rng(seed).standard_normal((M, N))
    return core.step(W)


# ── feature packing ────────────────────────────────────────────────────
def test_packet_feature_dim_formula():
    assert packet_feature_dim(M, N, R) == M * R + R * N + R * R + 9


def test_pack_packet_shape():
    f = pack_packet(_packet(), M, N, R)
    assert f.shape == (packet_feature_dim(M, N, R),)
    assert f.dtype == np.float64


def test_pack_packet_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="packet shape mismatch"):
        pack_packet(_packet(), M + 1, N, R)


def test_pack_packet_does_not_mutate():
    p = _packet()
    ub_before = p.Ub.copy()
    _ = pack_packet(p, M, N, R)
    assert np.array_equal(p.Ub, ub_before)


# ── carrier construction ───────────────────────────────────────────────
def test_carrier_forward_shape_prefix():
    c = SubstrateCarrier(M, N, R, output_shape=(4, 32), hidden_dim=64)
    out = c(_packet())
    assert out.shape == (4, 32)


def test_carrier_forward_shape_gates():
    c = SubstrateCarrier(M, N, R, output_shape=(6,), hidden_dim=64)
    out = c(_packet())
    assert out.shape == (6,)


def test_carrier_zero_init_is_identity():
    """Zero-initialized output means no modulation at step 0."""
    c = SubstrateCarrier(M, N, R, output_shape=(32,), hidden_dim=64)
    out = c(_packet())
    assert torch.allclose(out, torch.zeros_like(out))


def test_carrier_extra_dim():
    c = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, extra_dim=8)
    out = c(_packet(), extra=np.zeros(8))
    assert out.shape == (16,)


def test_carrier_extra_required_when_declared():
    c = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, extra_dim=8)
    with pytest.raises(ValueError, match="extra"):
        c(_packet())


def test_carrier_extra_wrong_size():
    c = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, extra_dim=8)
    with pytest.raises(ValueError, match="extra feature size"):
        c(_packet(), extra=np.zeros(7))


# ── gradient flow ──────────────────────────────────────────────────────
def test_gradient_flows_into_carrier():
    c = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, extra_dim=4,
                         zero_init_output=False)
    p = _packet()
    extra = np.random.default_rng(0).standard_normal(4)
    out = c(p, extra=extra)
    target = torch.ones_like(out)
    loss = ((out - target) ** 2).mean()
    loss.backward()
    grads = [p.grad for p in c.parameters() if p.requires_grad]
    assert len(grads) > 0
    assert all(g is not None for g in grads)
    # At least one grad must be nonzero — the carrier actually learned something.
    assert any(float(g.abs().sum()) > 0.0 for g in grads)


def test_no_gradient_into_packet_arrays():
    """
    The packet is NumPy, so it cannot carry autograd. This test asserts
    the carrier's forward pass does not convert packet arrays into
    trainable tensors.
    """
    p = _packet()
    c = SubstrateCarrier(M, N, R, output_shape=(16,), hidden_dim=64)
    out = c(p)
    # Output is a tensor whose grad_fn chain does not include the packet.
    # Since packet is a dataclass of numpy arrays, there is nothing to
    # backprop into. Confirm the packet's arrays are still numpy.
    assert isinstance(p.Ub, np.ndarray)
    assert isinstance(p.Vb, np.ndarray)
    assert isinstance(p.Lambda, np.ndarray)


# ── determinism ────────────────────────────────────────────────────────
def test_carrier_deterministic_with_same_seed():
    a = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, seed=42, zero_init_output=False)
    b = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, seed=42, zero_init_output=False)
    p = _packet()
    assert torch.allclose(a(p), b(p))


def test_carrier_differs_with_different_seed():
    a = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, seed=1, zero_init_output=False)
    b = SubstrateCarrier(M, N, R, output_shape=(16,),
                         hidden_dim=64, seed=2, zero_init_output=False)
    p = _packet()
    assert not torch.allclose(a(p), b(p))


# ── state dict ─────────────────────────────────────────────────────────
def test_state_dict_roundtrip(tmp_path):
    c1 = SubstrateCarrier(M, N, R, output_shape=(16,),
                          hidden_dim=64, extra_dim=4,
                          zero_init_output=False, seed=0)
    p = _packet()
    extra = np.zeros(4)
    out_before = c1(p, extra=extra).detach().numpy()

    path = tmp_path / "carrier.pt"
    torch.save(c1.state_dict(), path)

    c2 = SubstrateCarrier(M, N, R, output_shape=(16,),
                          hidden_dim=64, extra_dim=4,
                          zero_init_output=False, seed=1)
    c2.load_state_dict(torch.load(path))
    out_after = c2(p, extra=extra).detach().numpy()

    assert np.allclose(out_before, out_after, atol=1e-6)
