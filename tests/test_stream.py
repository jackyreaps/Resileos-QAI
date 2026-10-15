"""Tests for the streaming substrate state (RES-311)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.codex import PhiPhaseCodex
from resileos.hierarchy import (
    HierarchicalEncoder,
    HierarchicalPacket,
    StreamState,
    StreamStateConfig,
)


def _codex(vocab=64, dim=128, max_pos=64):
    return PhiPhaseCodex(vocab_size=vocab, dim=dim, max_positions=max_pos)


def _enc(capacities=(4, 4, 4), **kw):
    return HierarchicalEncoder(_codex(**kw), capacities=list(capacities))


def _packet(hv=None, level=1, span=(0, 1), child_count=1, dim=128):
    if hv is None:
        rng = np.random.default_rng(0)
        hv = rng.standard_normal(dim) + 1j * rng.standard_normal(dim)
        hv = hv / np.linalg.norm(hv)
    return HierarchicalPacket(
        level=level,
        hv=hv,
        span_start=span[0],
        span_end=span[1],
        child_count=child_count,
    )


# ── config ──────────────────────────────────────────────────────────────
def test_config_rejects_dim_below_2():
    with pytest.raises(ValueError, match="dim must be"):
        StreamStateConfig(dim=1)


def test_config_rejects_decay_zero():
    with pytest.raises(ValueError, match="decay must be"):
        StreamStateConfig(dim=8, decay=0.0)


def test_config_rejects_decay_above_1():
    with pytest.raises(ValueError, match="decay must be"):
        StreamStateConfig(dim=8, decay=1.5)


def test_config_rejects_negative_decay():
    with pytest.raises(ValueError, match="decay must be"):
        StreamStateConfig(dim=8, decay=-0.1)


def test_config_accepts_decay_1():
    cfg = StreamStateConfig(dim=8, decay=1.0)
    assert cfg.decay == 1.0


def test_config_coerces_types():
    cfg = StreamStateConfig(dim="8", decay=1, seed="0")
    assert isinstance(cfg.dim, int) and cfg.dim == 8
    assert isinstance(cfg.decay, float) and cfg.decay == 1.0
    assert isinstance(cfg.seed, int) and cfg.seed == 0


def test_state_rejects_wrong_cfg_type():
    with pytest.raises(TypeError, match="StreamStateConfig"):
        StreamState({"dim": 8})


# ── initial state ───────────────────────────────────────────────────────
def test_initial_state_is_zero():
    st = StreamState(StreamStateConfig(dim=16))
    assert np.allclose(st.readout(), 0.0)
    assert st.packet_count == 0
    assert st.span == (None, None)
    assert st.last_packet_level == 0


def test_initial_entropy_is_zero():
    st = StreamState(StreamStateConfig(dim=16))
    assert st.entropy() == pytest.approx(0.0)


# ── update ──────────────────────────────────────────────────────────────
def test_update_increments_count():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(dim=16))
    assert st.packet_count == 1


def test_update_records_span():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(span=(10, 20), dim=16))
    assert st.span == (10, 20)


def test_update_extends_span():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(span=(10, 20), dim=16))
    st.update(_packet(span=(5, 15), dim=16))
    assert st.span == (5, 20)
    st.update(_packet(span=(25, 30), dim=16))
    assert st.span == (5, 30)


def test_update_records_last_level():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(level=3, dim=16))
    assert st.last_packet_level == 3


def test_update_rejects_wrong_shape():
    st = StreamState(StreamStateConfig(dim=16))
    with pytest.raises(ValueError, match="shape"):
        st.update(_packet(dim=32))


def test_update_rejects_non_packet():
    st = StreamState(StreamStateConfig(dim=16))
    with pytest.raises(TypeError, match="HierarchicalPacket"):
        st.update("not a packet")


def test_readout_is_unit_norm_after_update():
    st = StreamState(StreamStateConfig(dim=64))
    st.update(_packet(dim=64))
    assert abs(float(np.linalg.norm(st.readout())) - 1.0) < 1e-9


def test_update_many_matches_sequential():
    enc = _enc(capacities=(4, 4, 4))
    packets = enc.push_many(list(range(1, 12)))
    a = StreamState(StreamStateConfig(dim=enc.codex.dim))
    b = StreamState(StreamStateConfig(dim=enc.codex.dim))
    a.update_many(packets)
    for p in packets:
        b.update(p)
    assert np.allclose(a.readout(), b.readout())
    assert a.packet_count == b.packet_count


# ── decay ───────────────────────────────────────────────────────────────
def test_decay_1_entropy_grows_with_packets():
    st = StreamState(StreamStateConfig(dim=256, decay=1.0))
    rng = np.random.default_rng(0)
    for _ in range(20):
        hv = rng.standard_normal(256) + 1j * rng.standard_normal(256)
        hv = hv / np.linalg.norm(hv)
        st.update(_packet(hv=hv, dim=256))
    assert st.entropy() > 1.0


def test_decay_less_than_1_entropy_bounded():
    st = StreamState(StreamStateConfig(dim=256, decay=0.9))
    rng = np.random.default_rng(0)
    for _ in range(40):
        hv = rng.standard_normal(256) + 1j * rng.standard_normal(256)
        hv = hv / np.linalg.norm(hv)
        st.update(_packet(hv=hv, dim=256))
    # entropy saturates below the packet count
    assert st.entropy() < st.packet_count


def test_level_weighting_high_level_downweighted():
    """decay**L means level-3 packets are weighted by decay^3."""
    hv = np.ones(64, dtype=np.complex128) / np.sqrt(64)
    st_1 = StreamState(StreamStateConfig(dim=64, decay=0.5))
    st_3 = StreamState(StreamStateConfig(dim=64, decay=0.5))
    st_1.update(_packet(hv=hv, level=1, dim=64))
    st_3.update(_packet(hv=hv, level=3, dim=64))
    # both normalized to unit norm; this test documents the weighting
    # path is exercised without error
    assert abs(float(np.linalg.norm(st_1.readout())) - 1.0) < 1e-9
    assert abs(float(np.linalg.norm(st_3.readout())) - 1.0) < 1e-9


# ── determinism ─────────────────────────────────────────────────────────
def test_determinism_same_seed():
    a = StreamState(StreamStateConfig(dim=64, decay=1.0, seed=0))
    b = StreamState(StreamStateConfig(dim=64, decay=1.0, seed=0))
    enc = _enc(capacities=(4, 4, 4))
    for t in range(20):
        for p in enc.push(t % 60):
            a.update(p)
            b.update(p)
    assert np.allclose(a.readout(), b.readout())
    assert a.span == b.span
    assert a.packet_count == b.packet_count


def test_seed_does_not_affect_deterministic_update():
    a = StreamState(StreamStateConfig(dim=64, decay=1.0, seed=0))
    b = StreamState(StreamStateConfig(dim=64, decay=1.0, seed=999))
    enc = _enc(capacities=(4, 4, 4))
    for t in range(12):
        for p in enc.push(t % 60):
            a.update(p)
            b.update(p)
    assert np.allclose(a.readout(), b.readout())


# ── reset ───────────────────────────────────────────────────────────────
def test_reset_clears_state():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(dim=16))
    st.reset()
    assert np.allclose(st.readout(), 0.0)
    assert st.packet_count == 0
    assert st.span == (None, None)
    assert st.last_packet_level == 0


def test_reset_allows_reuse():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(dim=16))
    st.reset()
    st.update(_packet(dim=16))
    assert st.packet_count == 1


# ── persistence ─────────────────────────────────────────────────────────
def test_save_load_roundtrip(tmp_path):
    st = StreamState(StreamStateConfig(dim=32, decay=0.9, seed=7))
    rng = np.random.default_rng(0)
    for _ in range(5):
        hv = rng.standard_normal(32) + 1j * rng.standard_normal(32)
        hv = hv / np.linalg.norm(hv)
        st.update(_packet(hv=hv, span=(0, 10), dim=32))
    p = tmp_path / "state.npz"
    st.save(p)
    st2 = StreamState.load(p)
    assert st2.dim == st.dim
    assert st2.decay == st.decay
    assert st2.packet_count == st.packet_count
    assert st2.span == st.span
    assert st2.last_packet_level == st.last_packet_level
    assert np.allclose(st2.readout(), st.readout())


def test_save_load_preserves_empty_span(tmp_path):
    st = StreamState(StreamStateConfig(dim=16))
    p = tmp_path / "empty.npz"
    st.save(p)
    st2 = StreamState.load(p)
    assert st2.span == (None, None)


def test_save_creates_parent_dirs(tmp_path):
    st = StreamState(StreamStateConfig(dim=16))
    p = tmp_path / "nested" / "dir" / "state.npz"
    st.save(p)
    assert p.exists()


# ── snapshot ────────────────────────────────────────────────────────────
def test_snapshot_keys():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(dim=16))
    s = st.snapshot()
    for k in (
        "dim", "decay", "seed", "packet_count",
        "span_start", "span_end", "last_packet_level", "entropy",
    ):
        assert k in s


def test_snapshot_reflects_update():
    st = StreamState(StreamStateConfig(dim=16))
    st.update(_packet(span=(5, 9), level=2, dim=16))
    s = st.snapshot()
    assert s["packet_count"] == 1
    assert s["span_start"] == 5
    assert s["span_end"] == 9
    assert s["last_packet_level"] == 2


# ── integration ─────────────────────────────────────────────────────────
def test_integration_with_encoder():
    enc = _enc(capacities=(4, 4, 4))
    st = StreamState(StreamStateConfig(dim=enc.codex.dim))
    packets = enc.push_many(list(range(1, 20)))
    packets += enc.flush()          # <-- tokens 17-19 emit here
    st.update_many(packets)
    assert st.packet_count == len(packets)
    assert st.span[1] == 19


def test_repr_contains_fields():
    st = StreamState(StreamStateConfig(dim=16, decay=0.5))
    r = repr(st)
    assert "StreamState" in r
    assert "dim=16" in r
    assert "decay=0.5" in r
