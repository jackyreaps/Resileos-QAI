"""Tests for the layered mask stack (RES-312, prime tower carriers)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.hierarchy.mask import (
    DEFAULT_K,
    FEATURE_BITS,
    K_MIN,
    MaskLayer,
    MaskStack,
    MaskStackConfig,
    layer_carrier,
    tower_level_for,
)


def _cfg(**kw):
    base = dict(dim=64, k=4, n_layers=3, local_first=True, seed=0)
    base.update(kw)
    return MaskStackConfig(**base)


def _stack(**kw):
    return MaskStack(_cfg(**kw))


# ── config ──────────────────────────────────────────────────────────────
def test_config_rejects_dim_below_4():
    with pytest.raises(ValueError, match="dim must be"):
        MaskStackConfig(dim=2)


def test_config_rejects_k_below_min():
    with pytest.raises(ValueError, match="k must be"):
        MaskStackConfig(dim=64, k=K_MIN - 1)


def test_config_rejects_n_layers_zero():
    with pytest.raises(ValueError, match="n_layers must be"):
        MaskStackConfig(dim=64, n_layers=0)


def test_config_rejects_n_layers_exceeding_tower():
    """At dim=16, Nyquist is 8. Largest prime < 8 is 7 (p_4).
    Levels 2..4 -> 3 usable. n_layers=5 exceeds that."""
    with pytest.raises(ValueError, match="exceeds tower"):
        MaskStackConfig(dim=16, n_layers=5)


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


# ── tower_level_for ─────────────────────────────────────────────────────
def test_tower_level_local_first_ordering():
    """local_first=True: layer 0 = level 2 (smallest prime),
    layer n-1 = highest level."""
    l0 = tower_level_for(0, 3, local_first=True)
    l1 = tower_level_for(1, 3, local_first=True)
    l2 = tower_level_for(2, 3, local_first=True)
    assert l0 < l1 < l2
    assert l0 == 2


def test_tower_level_global_first_ordering():
    """local_first=False: layer 0 = highest level,
    layer n-1 = level 2."""
    l0 = tower_level_for(0, 3, local_first=False)
    l1 = tower_level_for(1, 3, local_first=False)
    l2 = tower_level_for(2, 3, local_first=False)
    assert l0 > l1 > l2
    assert l2 == 2


def test_tower_level_rejects_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        tower_level_for(5, 3, local_first=True)


def test_tower_level_rejects_bad_n_layers():
    with pytest.raises(ValueError, match="n_layers must be"):
        tower_level_for(0, 0, local_first=True)


# ── layer_carrier ───────────────────────────────────────────────────────
def test_layer_carrier_unit_norm():
    c = layer_carrier(0, 3, 64, local_first=True)
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-9


def test_layer_carrier_rejects_bad_dim():
    with pytest.raises(ValueError, match="dim must be"):
        layer_carrier(0, 3, 2)


def test_layer_carrier_rejects_nyquist_violation():
    """At dim=16, Nyquist is 8. Prime 11 (p_5, level 5) exceeds it."""
    with pytest.raises(ValueError, match="Nyquist"):
        layer_carrier(3, 3, 16, local_first=True)


def test_layer_carrier_different_layers_differ():
    c0 = layer_carrier(0, 3, 64, local_first=True)
    c1 = layer_carrier(1, 3, 64, local_first=True)
    assert not np.allclose(c0, c1)


def test_layer_carrier_deterministic():
    a = layer_carrier(2, 4, 128, local_first=True)
    b = layer_carrier(2, 4, 128, local_first=True)
    assert np.allclose(a, b)


def test_layer_carriers_near_orthogonal():
    """Prime-frequency carriers are near-orthogonal by construction.
    All pairwise correlations below 0.15 at dim=512."""
    n = 4
    dim = 512
    carriers = [
        layer_carrier(i, n, dim, local_first=True) for i in range(n)
    ]
    for i in range(n):
        for j in range(i + 1, n):
            ip = abs(float(np.real(np.vdot(carriers[i], carriers[j]))))
            assert ip < 0.15, (
                f"layers {i},{j} correlated at {ip:.4f}"
            )


def test_layer_carrier_local_first_inverts_global_first():
    """Same tower level appears at opposite ends when local_first flips."""
    c_local_first_0 = layer_carrier(0, 3, 64, local_first=True)
    c_global_first_2 = layer_carrier(2, 3, 64, local_first=False)
    assert np.allclose(c_local_first_0, c_global_first_2)


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
    they select the same features at two different tower levels."""
    st = _stack(n_layers=3)
    st.add_layer((True, True, True, False))
    st.add_layer((True, True, True, False))
    assert st.n_layers == 2
    assert st.layers[0].mask == st.layers[1].mask
    assert st.layers[0].tower_level != st.layers[1].tower_level


def test_default_weight_schedule():
    st = _stack(n_layers=3)
    l0 = st.add_layer((True, True, True, False))
    l1 = st.add_layer((True, True, False, False))
    assert l0.weight == pytest.approx(1.0)
    assert l1.weight == pytest.approx(0.5)


def test_add_layer_records_prime():
    st = _stack(n_layers=3, local_first=True)
    l0 = st.add_layer((True, True, True, False))
    l1 = st.add_layer((True, True, False, False))
    l2 = st.add_layer((True, False, False, False))
    # local_first: layer 0 = level 2 = prime 3; layer 1 = level 3 = prime 5;
    # layer 2 = level 4 = prime 7
    assert l0.prime == 3
    assert l1.prime == 5
    assert l2.prime == 7


def test_add_layer_records_branch():
    st = _stack(n_layers=4, local_first=True)
    l0 = st.add_layer((True, True, True, False))  # level 2, even
    l1 = st.add_layer((True, True, False, False))  # level 3, odd
    assert l0.branch == "even"
    assert l1.branch == "odd"


def test_orientation_methods():
    st = _stack(n_layers=3)
    st.add_layer((True, True, True, False))
    st.add_layer((True, True, False, False))
    st.add_layer((True, False, False, False))
    assert st.tower_levels() == [2, 3, 4]
    assert st.primes() == [3, 5, 7]
    assert st.branches() == ["even", "odd", "even"]


def test_is_forbidden():
    st = _stack(n_layers=3)
    st.add_layer((True, True, True, False))  # level 2, even
    st.add_layer((True, True, False, False))  # level 3, odd
    assert not st.is_forbidden(0)
    assert st.is_forbidden(1)


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


def test_encode_different_inputs_differ():
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


def test_encode_carriers_independent_of_mask():
    """The carrier is positional. Two stacks with the same config but
    different masks produce the same carriers."""
    s1 = _stack(dim=64, n_layers=3)
    s2 = _stack(dim=64, n_layers=3)
    s1.add_layer((True, True, True, False))
    s1.add_layer((True, True, False, False))
    s1.add_layer((True, False, False, False))
    s2.add_layer((True, True, True, True))
    s2.add_layer((True, True, True, False))
    s2.add_layer((True, True, False, False))
    for i in range(3):
        assert np.allclose(s1.layers[i].carrier, s2.layers[i].carrier)
        assert s1.layers[i].tower_level == s2.layers[i].tower_level
        assert s1.layers[i].prime == s2.layers[i].prime


# ── sheath criterion ────────────────────────────────────────────────────
def test_is_saturated_both_conditions():
    assert MaskStack.is_saturated(boundary_codim=0.3, depth=0.01)


def test_is_saturated_codim_only_not_enough():
    assert not MaskStack.is_saturated(boundary_codim=0.3, depth=0.2)


def test_is_saturated_depth_only_not_enough():
    assert not MaskStack.is_saturated(boundary_codim=1.5, depth=0.01)


def test_is_saturated_neither_condition():
    assert not MaskStack.is_saturated(boundary_codim=1.5, depth=0.5)


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
              "local_first", "tower_levels", "primes",
              "branches", "layers"):
        assert k in s
    assert s["layers"][0]["mask"] == [True, True, True, False]
    assert s["layers"][0]["prime"] == 3


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
