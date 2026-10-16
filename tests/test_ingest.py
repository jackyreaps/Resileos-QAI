"""Tests for source ingestion (RES-323).

Matches the phi-ladder implementation: quality_fn(packet, current_R),
field_R_fn, phi^(-level) folding, R-gated level acceptance.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.codex import PHI, PhiPhaseCodex
from resileos.hierarchy import (
    HierarchicalEncoder,
    HierarchicalPacket,
    StreamState,
    StreamStateConfig,
)
from resileos.titanos.ingest import (
    PHI_INV,
    IngestionConfig,
    IngestionResult,
    SourceIngestor,
    _default_quality,
    phi_weight,
)


# ── fixtures ────────────────────────────────────────────────────────────
class FakeTitanos:
    """Minimal Titanos substitute. Records learn() calls."""

    def __init__(self) -> None:
        self.facts: list[tuple[str, str, str]] = []

    def learn(self, s: str, r: str, o: str) -> None:
        self.facts.append((s, r, o))


def _make_ingestor(
    dim: int = 128,
    capacities: tuple = (4, 4, 4),
    cfg: IngestionConfig | None = None,
    with_titanos: bool = False,
    field_R_fn=None,
) -> SourceIngestor:
    codex = PhiPhaseCodex(vocab_size=128, dim=dim, max_positions=64)
    enc = HierarchicalEncoder(codex, capacities=list(capacities))
    stream = StreamState(StreamStateConfig(dim=dim))
    titanos = FakeTitanos() if with_titanos else None
    return SourceIngestor(
        enc, stream, titanos=titanos, cfg=cfg, field_R_fn=field_R_fn
    )


def _make_packet(
    hv: np.ndarray | None = None,
    level: int = 1,
    span: tuple = (0, 1),
    dim: int = 128,
) -> HierarchicalPacket:
    if hv is None:
        rng = np.random.default_rng(0)
        hv = rng.standard_normal(dim) + 1j * rng.standard_normal(dim)
        hv = hv / np.linalg.norm(hv)
    return HierarchicalPacket(
        level=level,
        hv=hv,
        span_start=span[0],
        span_end=span[1],
        child_count=1,
    )


# ── phi_weight ──────────────────────────────────────────────────────────
def test_phi_weight_level_0():
    assert phi_weight(0) == 1.0


def test_phi_weight_level_1():
    assert phi_weight(1) == pytest.approx(PHI_INV)


def test_phi_weight_monotone_decreasing():
    weights = [phi_weight(L) for L in range(8)]
    assert all(b <= a for a, b in zip(weights, weights[1:]))


def test_phi_weight_geometric():
    # phi^(-(L+1)) / phi^(-L) = phi^(-1) = PHI_INV
    for L in range(6):
        ratio = phi_weight(L + 1) / phi_weight(L)
        assert ratio == pytest.approx(PHI_INV)


def test_phi_weight_rejects_negative():
    with pytest.raises(ValueError, match="level"):
        phi_weight(-1)


# ── config ──────────────────────────────────────────────────────────────
def test_config_defaults():
    c = IngestionConfig()
    assert c.r_min == 0.5
    assert c.csi_min == 0.5
    assert c.max_per_source == 10000
    assert c.max_level_at_locked == 10
    assert c.max_level_at_mixed == 1
    assert c.max_level_at_exploring == 0
    assert c.locked_threshold == 0.9
    assert c.exploring_threshold == 0.3


def test_config_rejects_bad_r_min():
    with pytest.raises(ValueError, match="r_min"):
        IngestionConfig(r_min=1.5)


def test_config_rejects_bad_csi_min():
    with pytest.raises(ValueError, match="csi_min"):
        IngestionConfig(csi_min=-0.1)


def test_config_rejects_bad_max():
    with pytest.raises(ValueError, match="max_per_source"):
        IngestionConfig(max_per_source=0)


def test_config_rejects_mixed_above_locked():
    with pytest.raises(ValueError, match="max_level_at_mixed"):
        IngestionConfig(max_level_at_locked=1, max_level_at_mixed=5)


# ── construction ────────────────────────────────────────────────────────
def test_ingestor_rejects_bad_encoder():
    with pytest.raises(TypeError):
        SourceIngestor("not_encoder", "not_stream")


def test_ingestor_rejects_bad_stream():
    codex = PhiPhaseCodex(vocab_size=128, dim=128, max_positions=64)
    enc = HierarchicalEncoder(codex, capacities=[4, 4, 4])
    with pytest.raises(TypeError):
        SourceIngestor(enc, "not_stream")


def test_ingestor_rejects_dim_mismatch():
    codex = PhiPhaseCodex(vocab_size=128, dim=128, max_positions=64)
    enc = HierarchicalEncoder(codex, capacities=[4, 4, 4])
    stream = StreamState(StreamStateConfig(dim=64))
    with pytest.raises(ValueError, match="dim"):
        SourceIngestor(enc, stream)


# ── ingest basics ───────────────────────────────────────────────────────
def test_ingest_basic():
    ing = _make_ingestor()
    result = ing.ingest(list(range(1, 17)), source_id="test-1")
    assert isinstance(result, IngestionResult)
    assert result.source_id == "test-1"
    assert result.packets_emitted > 0
    assert result.packets_accepted > 0


def test_ingest_result_new_fields():
    ing = _make_ingestor()
    result = ing.ingest(list(range(1, 17)), source_id="test")
    assert hasattr(result, "field_R_at_ingest")
    assert hasattr(result, "max_level_accepted")


def test_ingest_blacklisted_source():
    cfg = IngestionConfig(source_blacklist=("bad-source",))
    ing = _make_ingestor(cfg=cfg)
    result = ing.ingest(list(range(1, 17)), source_id="bad-source")
    assert result.packets_emitted == 0
    assert result.rejection_reasons.get("blacklisted") == 1


def test_ingest_empty_tokens():
    ing = _make_ingestor()
    result = ing.ingest([], source_id="empty")
    assert result.packets_emitted == 0
    assert result.packets_accepted == 0


# ── quality_fn with new signature ───────────────────────────────────────
def test_quality_fn_receives_current_R():
    seen: list[float] = []

    def qfn(packet, current_R):
        seen.append(current_R)
        return (1.0, 1.0)

    ing = _make_ingestor(field_R_fn=lambda: 0.75)
    ing.ingest(list(range(1, 17)), source_id="t", quality_fn=qfn)
    assert seen
    assert all(R == 0.75 for R in seen)


def test_ingest_quality_fn_rejects_via_r():
    def never_accept(packet, current_R):
        return (0.0, 1.0)

    ing = _make_ingestor()
    result = ing.ingest(
        list(range(1, 17)), source_id="test", quality_fn=never_accept
    )
    assert result.packets_accepted == 0
    assert "r_below_min" in result.rejection_reasons


def test_ingest_quality_fn_rejects_via_csi():
    def csi_fail(packet, current_R):
        return (1.0, 0.0)

    ing = _make_ingestor()
    result = ing.ingest(
        list(range(1, 17)), source_id="test", quality_fn=csi_fail
    )
    assert result.packets_accepted == 0
    assert "csi_below_min" in result.rejection_reasons


def test_ingest_quality_fn_accepts_all():
    def always_accept(packet, current_R):
        return (1.0, 1.0)

    ing = _make_ingestor()
    result = ing.ingest(
        list(range(1, 17)), source_id="test", quality_fn=always_accept
    )
    assert result.packets_accepted == result.packets_emitted


# ── R gate on level ─────────────────────────────────────────────────────
def test_R_gate_locked_accepts_all_levels():
    # capacities (2,2,2), 8 tokens -> 4 L1 + 2 L2 + 1 L3 = 7 packets
    ing = _make_ingestor(
        capacities=(2, 2, 2), field_R_fn=lambda: 0.95
    )
    result = ing.ingest(list(range(1, 9)), source_id="t")
    assert result.field_R_at_ingest == 0.95
    assert result.packets_accepted == result.packets_emitted
    assert result.max_level_accepted == 3


def test_R_gate_mixed_limits_to_level_1():
    ing = _make_ingestor(
        capacities=(2, 2, 2), field_R_fn=lambda: 0.5
    )
    result = ing.ingest(list(range(1, 9)), source_id="t")
    assert result.field_R_at_ingest == 0.5
    assert result.max_level_accepted <= 1
    assert "level_above_R_gate" in result.rejection_reasons


def test_R_gate_exploring_rejects_all_above_0():
    ing = _make_ingestor(
        capacities=(2, 2, 2), field_R_fn=lambda: 0.1
    )
    result = ing.ingest(list(range(1, 9)), source_id="t")
    assert result.field_R_at_ingest == 0.1
    # max_level_at_exploring = 0, but encoder emits levels 1..3
    assert result.packets_accepted == 0
    assert "level_above_R_gate" in result.rejection_reasons


def test_no_field_R_fn_defaults_locked():
    ing = _make_ingestor(capacities=(2, 2, 2))
    result = ing.ingest(list(range(1, 9)), source_id="t")
    assert result.field_R_at_ingest == 1.0


# ── phi-ladder weighting ────────────────────────────────────────────────
def test_phi_weighting_lower_level_dominates():
    """Fold a level-1 packet followed by a level-5 packet. The readout
    should be more similar to the level-1 packet (phi^-1 >> phi^-5)."""
    hv_a = np.zeros(128, dtype=np.complex128)
    hv_a[0] = 1.0
    hv_b = np.zeros(128, dtype=np.complex128)
    hv_b[1] = 1.0

    p1 = _make_packet(hv=hv_a, level=1, span=(0, 1))
    p5 = _make_packet(hv=hv_b, level=5, span=(1, 2))

    ing = _make_ingestor()
    ing._fold(p1)
    ing._fold(p5)
    readout = ing.readout()

    sim_a = abs(float(np.real(np.vdot(hv_a, readout))))
    sim_b = abs(float(np.real(np.vdot(hv_b, readout))))
    assert sim_a > sim_b, (
        f"level-1 sim {sim_a:.4f} should beat level-5 sim {sim_b:.4f}"
    )


def test_phi_weighting_order_independent_winner():
    """Reverse the fold order. The level-1 packet should still dominate."""
    hv_a = np.zeros(128, dtype=np.complex128)
    hv_a[0] = 1.0
    hv_b = np.zeros(128, dtype=np.complex128)
    hv_b[1] = 1.0

    p1 = _make_packet(hv=hv_a, level=1, span=(0, 1))
    p5 = _make_packet(hv=hv_b, level=5, span=(1, 2))

    ing = _make_ingestor()
    ing._fold(p5)
    ing._fold(p1)
    readout = ing.readout()

    sim_a = abs(float(np.real(np.vdot(hv_a, readout))))
    sim_b = abs(float(np.real(np.vdot(hv_b, readout))))
    assert sim_a > sim_b


def test_fold_increments_packet_count():
    ing = _make_ingestor()
    assert ing.stream.packet_count == 0
    ing._fold(_make_packet(level=1))
    assert ing.stream.packet_count == 1
    ing._fold(_make_packet(level=2))
    assert ing.stream.packet_count == 2


def test_fold_records_span():
    ing = _make_ingestor()
    ing._fold(_make_packet(level=1, span=(10, 20)))
    assert ing.stream.span == (10, 20)
    ing._fold(_make_packet(level=1, span=(5, 15)))
    assert ing.stream.span == (5, 20)


# ── stream integration ──────────────────────────────────────────────────
def test_ingest_updates_stream():
    ing = _make_ingestor()
    assert ing.stream.packet_count == 0
    ing.ingest(list(range(1, 17)), source_id="test")
    assert ing.stream.packet_count > 0


def test_ingest_readout_is_unit_norm():
    ing = _make_ingestor()
    ing.ingest(list(range(1, 17)), source_id="test")
    hv = ing.readout()
    assert hv.shape == (128,)
    assert abs(float(np.linalg.norm(hv)) - 1.0) < 1e-9


def test_ingest_accumulates_across_calls():
    ing = _make_ingestor()
    ing.ingest(list(range(1, 17)), source_id="a")
    count_after_first = ing.stream.packet_count
    ing.ingest(list(range(17, 33)), source_id="b")
    assert ing.stream.packet_count > count_after_first


# ── max_per_source ──────────────────────────────────────────────────────
def test_ingest_max_per_source_enforced():
    cfg = IngestionConfig(max_per_source=1)
    ing = _make_ingestor(cfg=cfg, capacities=(2, 2, 2))
    result = ing.ingest(list(range(1, 17)), source_id="test")
    assert result.packets_accepted <= 1
    assert "max_per_source" in result.rejection_reasons


# ── extractor ───────────────────────────────────────────────────────────
def test_ingest_extractor_writes_facts():
    def extractor(packet):
        return [("alice", "knows", f"pkt_{packet.span_start}")]

    ing = _make_ingestor(with_titanos=True)
    result = ing.ingest(
        list(range(1, 17)), source_id="test", extractor=extractor
    )
    assert result.facts_written > 0
    assert len(ing.titanos.facts) == result.facts_written


def test_ingest_no_titanos_no_facts():
    def extractor(packet):
        return [("alice", "knows", "bob")]

    ing = _make_ingestor(with_titanos=False)
    result = ing.ingest(
        list(range(1, 17)), source_id="test", extractor=extractor
    )
    assert result.facts_written == 0


def test_ingest_no_extractor_no_facts():
    ing = _make_ingestor(with_titanos=True)
    result = ing.ingest(list(range(1, 17)), source_id="test")
    assert result.facts_written == 0
    assert len(ing.titanos.facts) == 0


def test_ingest_extractor_only_on_accepted():
    def reject_all(packet, current_R):
        return (0.0, 0.0)

    def extractor(packet):
        return [("x", "y", "z")]

    ing = _make_ingestor(with_titanos=True)
    result = ing.ingest(
        list(range(1, 17)),
        source_id="test",
        quality_fn=reject_all,
        extractor=extractor,
    )
    assert result.packets_accepted == 0
    assert result.facts_written == 0
    assert len(ing.titanos.facts) == 0


# ── serialization ───────────────────────────────────────────────────────
def test_result_to_dict_keys():
    ing = _make_ingestor()
    result = ing.ingest(list(range(1, 17)), source_id="test")
    d = result.to_dict()
    for k in (
        "source_id",
        "packets_emitted",
        "packets_accepted",
        "packets_rejected",
        "facts_written",
        "field_R_at_ingest",
        "max_level_accepted",
        "rejection_reasons",
    ):
        assert k in d


def test_snapshot_keys():
    ing = _make_ingestor()
    ing.ingest(list(range(1, 17)), source_id="test")
    s = ing.snapshot()
    assert "stream" in s
    assert "config" in s
    assert "phi_inv" in s
    for k in (
        "r_min",
        "csi_min",
        "coherence_min",
        "max_per_source",
        "source_blacklist",
        "max_level_at_locked",
        "max_level_at_mixed",
        "max_level_at_exploring",
        "locked_threshold",
        "exploring_threshold",
    ):
        assert k in s["config"]


# ── determinism ─────────────────────────────────────────────────────────
def test_ingest_deterministic_across_instances():
    a = _make_ingestor()
    b = _make_ingestor()
    a.ingest(list(range(1, 17)), source_id="test")
    b.ingest(list(range(1, 17)), source_id="test")
    assert np.allclose(a.readout(), b.readout())


def test_default_quality_accepts_everything():
    packet = _make_packet(level=3)
    r, csi = _default_quality(packet, 0.5)
    assert r == 1.0
    assert csi == 1.0
