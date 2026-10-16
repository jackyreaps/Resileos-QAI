"""Tests for hierarchical encoding (RES-310)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.codex import PhiPhaseCodex
from resileos.hierarchy import (
    HierarchicalEncoder,
    HierarchicalPacket,
    HierarchicalQuery,
    default_capacity,
    level_phasor,
)


def _codex(vocab=128, dim=128, max_pos=64):
    return PhiPhaseCodex(vocab_size=vocab, dim=dim, max_positions=max_pos)


# ── capacity ────────────────────────────────────────────────────────────
def test_default_capacity_dim512():
    assert 35 <= default_capacity(512) <= 45


def test_default_capacity_dim1024():
    assert 65 <= default_capacity(1024) <= 85


def test_default_capacity_monotone():
    caps = [default_capacity(d) for d in (128, 256, 512, 1024)]
    assert all(b >= a for a, b in zip(caps, caps[1:]))


def test_default_capacity_floor_at_8():
    assert default_capacity(4) == 8


# ── position codes ──────────────────────────────────────────────────────
def test_level_phasor_unit_norm():
    codes = level_phasor(np.arange(0, 8), dim=64, level=0)
    norms = np.linalg.norm(codes, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-9)


def test_level_phasor_cross_level_orthogonal():
    a = level_phasor(np.arange(0, 32), dim=256, level=0)
    b = level_phasor(np.arange(0, 32), dim=256, level=1)
    dots = np.abs(np.real(np.sum(np.conj(a) * b, axis=1)))
    assert np.all(dots < 0.25)


# ── encoder config validation ───────────────────────────────────────────
def test_encoder_rejects_empty_capacities():
    with pytest.raises(ValueError, match="non-empty"):
        HierarchicalEncoder(_codex(), capacities=[])


def test_encoder_rejects_capacity_below_2():
    with pytest.raises(ValueError, match=">= 2"):
        HierarchicalEncoder(_codex(), capacities=[1, 4])


def test_encoder_rejects_capacity_above_max_positions():
    codex = _codex(max_pos=16)
    with pytest.raises(ValueError, match="max_positions"):
        HierarchicalEncoder(codex, capacities=[32, 32])


# ── encoder basics ──────────────────────────────────────────────────────
def test_encoder_no_packet_before_capacity():
    enc = HierarchicalEncoder(_codex(), capacities=[8, 8])
    for t in range(7):
        assert enc.push(t) == []


def test_encoder_flushes_at_capacity():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4, 4])
    packets = enc.push_many([1, 2, 3, 4])
    assert len(packets) == 1
    p = packets[0]
    assert isinstance(p, HierarchicalPacket)
    assert p.level == 1
    assert p.child_count == 4
    assert p.span_start == 0
    assert p.span_end == 4


def test_encoder_packet_hv_unit_norm():
    codex = _codex()
    enc = HierarchicalEncoder(codex, capacities=[4, 4, 4])
    p = enc.push_many([1, 2, 3, 4])[0]
    assert p.hv.shape == (codex.dim,)
    assert abs(float(np.linalg.norm(p.hv)) - 1.0) < 1e-9


def test_encoder_cascade_emits_multiple_packets():
    enc = HierarchicalEncoder(_codex(), capacities=[2, 2, 2])
    packets = enc.push_many(list(range(8)))
    levels = sorted(p.level for p in packets)
    assert levels == [1, 1, 1, 1, 2, 2, 3]


def test_encoder_top_level_packet_span():
    enc = HierarchicalEncoder(_codex(), capacities=[2, 2, 2])
    packets = enc.push_many(list(range(8)))
    top = [p for p in packets if p.level == 3][0]
    assert top.span_start == 0
    assert top.span_end == 8
    assert top.child_count == 2


def test_encoder_rejects_out_of_vocab():
    enc = HierarchicalEncoder(_codex(vocab=16), capacities=[4, 4])
    with pytest.raises(ValueError, match="out of vocab"):
        enc.push(20)


def test_encoder_reset_clears_state():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4])
    enc.push_many([1, 2, 3])
    enc.reset()
    assert enc.token_count == 0
    assert all(len(b) == 0 for b in enc._buffers)


# ── flush ───────────────────────────────────────────────────────────────
def test_flush_partial_returns_all_levels():
    enc = HierarchicalEncoder(_codex(), capacities=[8, 8, 8])
    enc.push_many([1, 2, 3, 4, 5])
    packets = enc.flush()
    levels = sorted(p.level for p in packets)
    assert levels == [1, 2, 3]
    top = [p for p in packets if p.level == 3][0]
    assert top.span_start == 0
    assert top.span_end == 5


def test_flush_empty_returns_empty_list():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4])
    assert enc.flush() == []


def test_flush_cascades_when_upper_fills():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4, 4])
    enc.push_many(list(range(7)))
    packets = enc.flush()
    assert [p.level for p in packets] == [1, 2, 3]


# ── query ───────────────────────────────────────────────────────────────
def test_query_locate_recovers_position():
    codex = _codex(vocab=32, dim=256)
    enc = HierarchicalEncoder(codex, capacities=[2, 2, 2])
    # 8 tokens fill level 3 exactly
    packets = enc.push_many([3, 5, 7, 11, 13, 17, 19, 23])
    top = [p for p in packets if p.level == 3][0]
    q = HierarchicalQuery(enc)
    target = q.retrieve(top.hv, pos_level=2, position=0)
    pos, sim = q.locate(top.hv, pos_level=2, target_hv=target)
    assert pos == 0
    assert sim > 0.5


def test_query_rejects_bad_pos_level():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4])
    q = HierarchicalQuery(enc)
    with pytest.raises(ValueError, match="pos_level"):
        q.retrieve(np.zeros(64, dtype=np.complex128), pos_level=5, position=0)


def test_query_rejects_bad_position():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4])
    q = HierarchicalQuery(enc)
    with pytest.raises(ValueError, match="position"):
        q.retrieve(np.zeros(64, dtype=np.complex128), pos_level=0, position=99)


def test_query_rejects_bad_path_length():
    enc = HierarchicalEncoder(_codex(), capacities=[4, 4, 4])
    q = HierarchicalQuery(enc)
    packet = HierarchicalPacket(
        level=2,
        hv=np.zeros(64, dtype=np.complex128),
        span_start=0,
        span_end=4,
        child_count=2,
    )
    with pytest.raises(ValueError, match="path length"):
        q.descend_to_token(packet, path=[0, 0, 0])


def test_query_descend_single_path():
    codex = _codex(vocab=128, dim=512)
    enc = HierarchicalEncoder(codex, capacities=[4, 4, 4])
    tokens = list(range(1, 65))
    packets = enc.push_many(tokens)
    top = [p for p in packets if p.level == 3][0]
    q = HierarchicalQuery(enc)
    token_id, _ = q.descend_to_token(top, path=[0, 0, 0])
    assert token_id == 1


def test_query_descend_all_paths_recall():
    codex = _codex(vocab=128, dim=512)
    cap = 4
    enc = HierarchicalEncoder(codex, capacities=[cap, cap, cap])
    tokens = list(range(1, cap ** 3 + 1))
    packets = enc.push_many(tokens)
    top = [p for p in packets if p.level == 3][0]
    q = HierarchicalQuery(enc)
    hits = 0
    total = 0
    for i in range(cap):
        for j in range(cap):
            for k in range(cap):
                idx = i * cap * cap + j * cap + k
                expected = tokens[idx]
                got, _ = q.descend_to_token(top, path=[i, j, k])
                total += 1
                if got == expected:
                    hits += 1
    acc = hits / total
    assert acc > 0.9, f"descent accuracy {acc:.2f} below 0.9"
