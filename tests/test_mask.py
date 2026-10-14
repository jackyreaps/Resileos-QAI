"""Tests for the layered mask stack (RES-312)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.codex import PHI
from resileos.hierarchy.mask import (
    DEFAULT_K,
    FEATURE_BITS,
    K_MIN,
    MaskLayer,
    MaskStack,
    MaskStackConfig,
    exponent_for,
    layer_carrier,
)


def _cfg(**kw):
    base = dict(dim=64, k=4, n_layers=3, local_first=True, seed=0)
    base.update(kw)
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
    cfg = MaskStackConfig(dim="64", k="4", n_layers="3", local_first=1)
    assert isinstance(cfg.dim, int) and cfg.dim == 64
    assert isinstance(cfg.k, int) and cfg.k == 4
    assert isinstance(cfg.local_first, bool) and cfg.local_first is True


def test_stack_rejects_wrong_cfg_type():
    with pytest.raises(TypeError, match="MaskStackConfig"):
        MaskStack({"dim": 64})


def test_feature_bits_length():
    assert len(FEATURE_BITS) == K_MIN


# ── exponent_for ────────────────────────────────────────────────────────
def test_exponent_local_first_ordering():
    # layer 0 = local -> highest exponent; layer n-1 = global -> lowest
    e0 = exponent_for(0, 3, local_first=True)
    e1 = exponent_for(1, 3, local_first=True)
    e2 = exponent_for(2, 3, local_first=True)
    assert e0 > e1 > e2


def test_exponent_global_first_ordering():
    # layer 0 = global -> lowest; layer n-1 = local -> highest
    e0 = exponent_for(0, 3, local_first=False)
    e1 = exponent_for(1, 3, local_first=False)
    e2 = exponent_for(2, 3, local_first=False)
    assert e0 < e1 < e2


def test_exponent_rejects_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        exponent_for(5, 3, local_first=True)


def test_exponent_rejects_bad_n_layers():
    with pytest.raises(ValueError, match="n_layers must be"):
        exponent_for(0, 0, local_first=True)


# ── layer_carrier ───────────────────────────────────────────────────────
def test_layer_carrier_unit_norm():
    c = layer_carrier(0, 3, 64, local_first=True)
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-9


def test_layer_carrier_rejects_bad_dim():
    with pytest.raises(ValueError, match="dim must be"):
        layer_carrier(0, 3, 1)


def test_layer_carrier_different_layers_differ():
    c0 = layer_carrier(0, 3, 64, local_first=True)
    c1 = layer_carrier(1, 3, 64, local_first=True)
    assert not np.allclose(c0, c1)


def test_layer_carrier_deterministic():
    a = layer_carrier(2, 4, 128, local_first=True)
    b = layer_carrier(2, 4, 128, local_first=True)
    assert np.allclose(a, b)


def test_layer_carriers_near_orthogonal():
    """Adjacent φ-power layers correlate at ~1/dim. All pairwise
    correlations below 0.1 for dim=512."""
    n = 4
    dim = 512
    carriers = [
        layer_carrier(i, n, dim, local_first=True) for i in range(n)
    ]
    for i in range(n):
        for j in range(i + 1, n):
            ip = abs(float(np.real(np.vdot(carriers[i], carriers[j]))))
            assert ip < 0.1, (
                f"layers {i},{j} correlated at {ip:.4f}"
            )


def test_layer_carrier_local_first_inverts_global_first():
    """Same exponent appears at opposite ends when local_first flips."""
    c_local_first_0 = layer_carrier(0, 3, 64, local_first=True)
    c_global_first_2 = layer_carrier(2, 3, 64, local_first=False)
    # layer 0 under local_first and layer 2 under global_first
    # both get the same exponent (n_layers - 0 + 1 = n_layers - 2 + 2 = 4)
    assert np.allclose(c_local_first_0, c_global_first_2)


def test_layer_carrier_exponents_irrational():
    """Adjacent multipliers differ by a φ-power, so their fractional
    parts are never integers."""
    n = 5
    exponents = [exponent_for(i, n, local_first=True) for i in range(n)]
    multipliers = [PHI ** e for e in exponents]
    for i in range(n - 1):
        diff = multipliers[i] - multipliers[i + 1]
        frac = abs(diff - round(diff))
        assert frac > 0.05, (
            f"layers {i},{i+1} differ by near-integer {diff:.4f}"
        )


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


def test_add_layer_rejects_when_full():
    st = _stack(n_layers=2)
    st.add_layer((True, True, True, False))
    st.add_layer((True, True, False, False))
    with pytest.raises(ValueError, match="stack full"):
        st.add_layer((True, False, False, False))


def test_add_layer_accepts_duplicate_mask():
    """With positional carriers, duplicate masks are meaningful:
    they select the same features at two different axis positions."""
    st = _stack(n_layers=3)
    st.add_layer((True, True, True, False))
    st.add_layer((True, True, True, False))
    assert st.n_layers == 2
    assert st.layers[0].mask == st.layers[1].mask
    assert st.layers[0].exponent != st.layers[1].exponent


def test_default_weight_schedule():
    st = _stack(n_layers=3)
    l0 = st.add_layer((True, True, True, False))
    l1 = st.add_layer((True, True, False, False))
    assert l0.weight == pytest.approx(1.0)
    assert l1.weight == pytest.approx(0.5)


def test_add_layer_records_exponent():
    st = _stack(n_layers=3, local_first=True)
    l0 = st.add_layer((True, True, True, False))
    l2 = st.add_layer((True, True, False, False))
    l3 = st.add_layer((True, False, False, False))
    # layer 0 = local -> highest exponent
    assert l0.exponent > l2.exponent > l3.exponent


def test_exponents_method():
    st = _stack(n_layers=3)
    st.add_layer((True, True, True, False))
    st.add_layer((True, True, False, False))
    st.add_layer((True, False, False, False))
    exps = st.exponents()
    assert len(exps) == 3
    assert exps[0] > exps[1] > exps[2]


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


def test_encode_carriers_do_not_depend_on_mask():
    """The carrier is positional. Two stacks with the same config but
    different masks produce the same carriers."""
    s1 = _stack(dim=64, n_layers=3)
    s2 = _stack(dim=64, n_layers=3)
    s1.add_layer((True, True, True, False))
    s1.add_layer((True, True, False, False))
    s1.add_layer((True, False, False, False))
    s2.add_layer((True, True, True, True))     # different masks
    s2.add_layer((True, True, True, False))
    s2.add_layer((True, True, False, False))
    for i in range(3):
        assert np.allclose(s1.layers[i].carrier, s2.layers[i].carrier)
        assert s1.layers[i].exponent == s2.layers[i].exponent


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
    for k in ("dim", "k", "n_layers_max", "n_layers",
              "local_first", "exponents", "layers"):
        assert k in s
    assert s["layers"][0]["mask"] == [True, True, True, False]
    assert s["layers"][0]["exponent"] == s["exponents"][0]


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
