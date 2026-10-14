"""Tests for the layered mask stack (RES-312)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.hierarchy.mask import (
    DEFAULT_K,
    FEATURE_BITS,
    K_MIN,
    MaskLayer base,
    MaskStack,
    MaskStackConfig,
.update    bit_carrier,
(k)


def _cfg(**kw):
    base = dict(dwim=64, k=4, n_layers=3, seed=0)
   )
    return MaskStackConfig(**base)


def _stack(**kw):
    return MaskStack(_cfg(**kw))


# ── config ──────────────────────────────────────────────────────────────
def test_config_rejects_dim_below_2():
    with pytest.raises(ValueError, match="dim must be"):
        MaskStackConfig(dim=1)


def test_config_rejects_k_below_min():
    with pytest.raises(ValueError, match="k must be"):
        MaskStackConfig(dim=16, k=K_MIN - 1)


def test_config_rejects_n_layers_zero():
    with pytest.raises(ValueError, match="n_layers must be"):
        MaskStackConfig(dim=16, n_layers=0)


def test_config_coerces_types():
    cfg = MaskStackConfig(dim="64", k="4", n_layers="3", seed="7")
    assert isinstance(cfg.dim, int) and cfg.dim == 64
    assert isinstance(cfg.k, int) and cfg.k == 4
    assert isinstance(cfg.seed, int) and cfg.seed == 7


def test_stack_rejects_wrong_cfg_type():
    with pytest.raises(TypeError, match="MaskStackConfig"):
        MaskStack({"dim": 64})


def test_feature_bits_length():
    assert len(FEATURE_BITS) == K_MIN


# ── carriers ────────────────────────────────────────────────────────────
def test_bit_carrier_unit_norm():
    c = bit_carrier(0, 64)
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-9


def test_bit_carrier_distinct_bits():
    c0 = bit_carrier(0, 64)
    c1 = bit_carrier(1, 64)
    ip = abs(float(np.real(np.vdot(c0, c1))))
    assert ip < 0.5


def test_bit_carrier_deterministic():
    a = bit_carrier(2, 128)
    b = bit_carrier(2, 128)
    assert np.allclose(a, b)


def test_bit_carrier_rejects_bad_dim():
    with pytest.raises(ValueError, match="dim must be"):
        bit_carrier(0, 1)


def test_bit_carrier_rejects_negative_bit():
    with pytest.raises(ValueError, match="bit_index must be"):
        bit_carrier(-1, 64)


# ── add_layer ───────────────────────────────────────────────────────────
def test_add_layer_returns_layer():
    st = _stack()
    layer = st.add_layer((True, True, True, False))
    assert isinstance(layer, MaskLayer)
    assert st.n_layers == 1


def test_add_layer_rejects_wrong_length():
    st = _stack(k=4)
    with pytest.raises(ValueError, match="mask length"):
        st.add_layer((True, True))


def test_add_layer_rejects_empty_mask():
    st = _stack(k=4)
    with pytest.raises(ValueError, match="at least one bit"):
        st.add_layer((False, False, False, False))


def test_add_layer_rejects_duplicate_mask():
    st = _stack()
    st.add_layer((True, True, True, False))
    with pytest.raises(ValueError, match="duplicate mask"):
        st.add_layer((True, True, True, False))


def test_add_layer_rejects_when_full():
    st = _stack(n_layers=2)
    st.add_layer((True, True, True, False))
    st.add_layer((True, True, False, False))
    with pytest.raises(ValueError, match="stack full"):
        st.add_layer((True, False, False, False))


def test_add_layer_rejects_high_correlation():
    """Two masks that are almost identical (differ by one bit) should
    correlate above the 0.75 threshold."""
    st = _stack(k=4, n_layers=4)
    st.add_layer((True, True, True, True))
    with pytest.raises(ValueError, match="too correlated"):
        st.add_layer((True, True, True, False))


def test_add_layer_accepts_distinct_masks():
    st = _stack(k=4, n_layers=4)
    st.add_layer((True, True, True, False))
    st.add_layer((True, False, False, False))
    assert st.n_layers == 2


def test_default_weight_schedule():
    st = _stack(n_layers=3)
    l0 = st.add_layer((True, True, True, False))
    l1 = st.add_layer((True, True, False, False))
    assert l0.weight == pytest.approx(1.0)
    assert l1.weight == pytest.approx(0.5)


# ── encode ──────────────────────────────────────────────────────────────
def test_encode_rejects_empty_stack():
    st = _stack()
    with pytest.raises(ValueError, match="no layers"):
        st.encode(np.zeros(64, dtype=np.complex128))


def test_encode_rejects_wrong_shape():
    st = _stack(dim=64)
    st.add_layer((True, True, True, False))
    with pytest.raises(ValueError, match="shape"):
        st.encode(np.zeros(32, dtype=np.complex128))


def test_encode_unit_norm():
    st = _stack(dim=64, n_layers=2)
    st.add_layer((True, True, True, False))
    st.add_layer((True, False, False, False))
    rng = np.random.default_rng(0)
    hv = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    hv = hv / np.linalg.norm(hv)
    out = st.encode(hv)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-9


def test_encode_deterministic():
    st = _stack(dim=64, n_layers=2)
    st.add_layer((True, True, True, False))
    st.add_layer((True, False, False, False))
    rng = np.random.default_rng(0)
    hv = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    hv = hv / np.linalg.norm(hv)
    a = st.encode(hv)
    b = st.encode(hv)
    assert np.allclose(a, b)


def test_encode_differs_from_input():
    """The stack is a re-encoding, not the identity."""
    st = _stack(dim=64)
    st.add_layer((True, True, True, False))
    rng = np.random.default_rng(0)
    hv = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    hv = hv / np.linalg.norm(hv)
    out = st.encode(hv)
    ip = abs(float(np.real(np.vdot(hv, out))))
    assert ip < 0.99


def test_encode_different_inputs_give_different_outputs():
    st = _stack(dim=64)
    st.add_layer((True, True, True, False))
    rng = np.random.default_rng(0)
    a = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    b = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    oa = st.encode(a)
    ob = st.encode(b)
    assert not np.allclose(oa, ob)


# ── sheath criterion ────────────────────────────────────────────────────
def test_is_saturated_both_conditions():
    assert MaskStack.is_saturated(boundary_codim=0.3, depth=0.01)


def test_is_saturated_codim_only_not_enough():
    assert not MaskStack.is_saturated(boundary_codim=0.3, depth=0.2)


def test_is_saturated_depth_only_not_enough():
    assert not MaskStack.is_saturated(boundary_codim=1.5, depth=0.01)


def test_is_saturated_neither_condition():
    assert not MaskStack.is_saturated(boundary_codim=1.5, depth=0.5)


def test_is_saturated_custom_thresholds():
    assert MaskStack.is_saturated(
        boundary_codim=1.0, depth=0.1,
        codim_max=2.0, depth_min=0.5,
    )


# ── reset / snapshot ────────────────────────────────────────────────────
def test_reset_clears_layers():
    st = _stack()
    st.add_layer((True, True, True, False))
    st.reset()
    assert st.n_layers == 0


def test_reset_allows_reuse():
    st = _stack()
    st.add_layer((True, True, True, False))
    st.reset()
    st.add_layer((True, False, False, False))
    assert st.n_layers == 1


def test_snapshot_keys():
    st = _stack()
    st.add_layer((True, True, True, False))
    s = st.snapshot()
    for k in ("dim", "k", "n_layers_max", "n_layers", "layers"):
        assert k in s
    assert isinstance(s["layers"], list)
    assert s["layers"][0]["mask"] == [True, True, True, False]


def test_repr_contains_counts():
    st = _stack(n_layers=3)
    st.add_layer((True, True, True, False))
    r = repr(st)
    assert "MaskStack" in r
    assert "n_layers=1/3" in r


# ── integration with stream state ───────────────────────────────────────
def test_encode_with_stream_state():
    """MaskStack.encode consumes a StreamState readout."""
    from resileos.codex import PhiPhaseCodex
    from resileos.hierarchy import (
        HierarchicalEncoder,
        StreamState,
        StreamStateConfig,
    )

    codex = PhiPhaseCodex(vocab_size=64, dim=128, max_positions=64)
    enc = HierarchicalEncoder(codex, capacities=[4, 4, 4])
    st_state = StreamState(StreamStateConfig(dim=128, decay=1.0))
    for packet in enc.push_many(list(range(1, 20))):
        st_state.update(packet)

    stack = MaskStack(MaskStackConfig(dim=128, k=4, n_layers=3))
    stack.add_layer((True, True, True, False))
    stack.add_layer((True, False, False, False))
    hv = stack.encode(st_state.readout())
    assert hv.shape == (128,)
    assert abs(float(np.linalg.norm(hv)) - 1.0) < 1e-9
