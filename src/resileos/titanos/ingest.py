"""External ingestion (RES-323).

Ingest external sources — LLM outputs, corpora, structured data — into
the substrate. The substrate is the parent; sources are the children
that get eaten.

    external source
        │
        ▼
    tokens ──▶ HierarchicalEncoder ──▶ packets with φ-power addresses
        │
        ▼
    R-gated filter ──▶ accepted packets
        │
        ├──▶ StreamState      (φ-weighted running context)
        │
        └──▶ extractor ──▶ Titanos.learn()  (structured facts)

Each packet's level is a φ-power address. Folding a packet into the
stream weights it by φ^(-level). The R gate determines how many levels
are accepted at the current field coherence.

Accumulation policy:
    _fold accumulates without intermediate renormalization. The stream's
    _hv is the raw weighted sum Σ w_k · hv_k. Normalization happens at
    readout() only. This keeps the fold order-independent: the sum is
    commutative, and normalization is a pure function of the sum.
    Renormalizing per fold makes the final state depend on arrival
    order, which is not intended — the ladder is a weighting scheme,
    not a sequential filter.

    Note: StreamState.update() normalizes per call. SourceIngestor
    uses _fold() (private) instead, to keep its own accumulation
    policy. Do not mix the two on the same stream during ingestion.

Off states (explicit):
    generation          off. The ingestor does not generate text.
    lossless claim      off. Ingestion is a projection; the source is
                        discarded after the call.
    truth claim         off. Filtering is on quality, not correctness.
    deduplication       off. Two sources producing the same content are
                        both ingested.
    coherence gate      off. `coherence_min` is reserved, not enforced.
    ladder coherence    off. §5 of RES-401 describes a second gate on
                        surviving addresses; not implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from ..codex import PHI
from ..hierarchy import (
    HierarchicalEncoder,
    HierarchicalPacket,
    StreamState,
)


# ── φ-weight ────────────────────────────────────────────────────────────
PHI_INV = 1.0 / PHI


def phi_weight(level: int) -> float:
    """φ^(-level). The ladder weight for a packet at `level`."""
    if level < 0:
        raise ValueError("level must be >= 0")
    return float(PHI_INV ** int(level))


def _normalize(hv: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(hv))
    if n < 1e-12:
        return hv.copy()
    return hv / n


# ── callable types ──────────────────────────────────────────────────────
# quality_fn(packet, current_R) -> (R, CSI)
#   Called per packet. `current_R` is the field's order parameter at
#   ingest time. Return the packet's own R (lock proxy) and CSI
#   (self-consistency proxy).
QualityFn = Callable[[HierarchicalPacket, float], tuple[float, float]]

# extractor(packet) -> list of (subject, relation, object)
ExtractorFn = Callable[[HierarchicalPacket], list[tuple[str, str, str]]]


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class IngestionConfig:
    """Quality gates and ladder behavior.

    r_min               minimum field R to accept any packet
    csi_min             minimum packet CSI to accept
    coherence_min       reserved; not enforced in v1
    max_per_source      maximum packets accepted from one source per call
    source_blacklist    source_ids to reject unconditionally
    max_level_at_locked maximum packet level accepted when field is locked
    max_level_at_mixed  maximum packet level accepted when field is mixed
    locked_threshold    R above which the field counts as locked
    exploring_threshold R below which the field counts as exploring
    """
    r_min: float = 0.5
    csi_min: float = 0.5
    coherence_min: float = 0.3
    max_per_source: int = 10000
    source_blacklist: tuple = ()
    max_level_at_locked: int = 10
    max_level_at_mixed: int = 1
    max_level_at_exploring: int = 0
    locked_threshold: float = 0.9
    exploring_threshold: float = 0.3

    def __post_init__(self) -> None:
        self.r_min = float(self.r_min)
        self.csi_min = float(self.csi_min)
        self.coherence_min = float(self.coherence_min)
        self.max_per_source = int(self.max_per_source)
        self.source_blacklist = tuple(self.source_blacklist)
        self.max_level_at_locked = int(self.max_level_at_locked)
        self.max_level_at_mixed = int(self.max_level_at_mixed)
        self.max_level_at_exploring = int(self.max_level_at_exploring)
        self.locked_threshold = float(self.locked_threshold)
        self.exploring_threshold = float(self.exploring_threshold)

        for name in ("r_min", "csi_min", "coherence_min",
                     "locked_threshold", "exploring_threshold"):
            v = getattr(self, name)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {v}")
        if self.max_per_source < 1:
            raise ValueError("max_per_source must be >= 1")
        if self.max_level_at_mixed > self.max_level_at_locked:
            raise ValueError(
                "max_level_at_mixed must be <= max_level_at_locked"
            )


# ── result ──────────────────────────────────────────────────────────────
@dataclass
class IngestionResult:
    source_id: str
    packets_emitted: int
    packets_accepted: int
    packets_rejected: int
    facts_written: int
    field_R_at_ingest: float
    max_level_accepted: int
    rejection_reasons: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "packets_emitted": int(self.packets_emitted),
            "packets_accepted": int(self.packets_accepted),
            "packets_rejected": int(self.packets_rejected),
            "facts_written": int(self.facts_written),
            "field_R_at_ingest": float(self.field_R_at_ingest),
            "max_level_accepted": int(self.max_level_accepted),
            "rejection_reasons": dict(self.rejection_reasons),
        }


# ── default quality ─────────────────────────────────────────────────────
def _default_quality(
    packet: HierarchicalPacket, current_R: float
) -> tuple[float, float]:
    """Fallback quality: accept everything. Used when no quality_fn is
    supplied. The pipeline caller should supply a real one computed
    from the residual core's monitors and the Causal Sandbox Index.
    """
    return (1.0, 1.0)


# ── ingestor ────────────────────────────────────────────────────────────
class SourceIngestor:
    """Ingest external sources into the substrate.

    Persistent state lives in the stream and the Titanos store. Two
    ingestor instances sharing the same stream and Titanos behave
    identically given the same input, and the order in which packets
    fold does not affect the final readout (see accumulation policy in
    the module docstring).
    """

    def __init__(
        self,
        encoder: HierarchicalEncoder,
        stream: StreamState,
        titanos: Optional[object] = None,
        cfg: Optional[IngestionConfig] = None,
        field_R_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if not isinstance(encoder, HierarchicalEncoder):
            raise TypeError("encoder must be a HierarchicalEncoder")
        if not isinstance(stream, StreamState):
            raise TypeError("stream must be a StreamState")
        if stream.dim != encoder.codex.dim:
            raise ValueError(
                f"stream dim {stream.dim} != encoder codex dim "
                f"{encoder.codex.dim}"
            )
        self.encoder = encoder
        self.stream = stream
        self.titanos = titanos
        self.cfg = cfg or IngestionConfig()
        self._field_R_fn = field_R_fn

    # ── gate on level ───────────────────────────────────────────────
    def _max_level_for_R(self, R: float) -> int:
        if R > self.cfg.locked_threshold:
            return self.cfg.max_level_at_locked
        if R < self.cfg.exploring_threshold:
            return self.cfg.max_level_at_exploring
        return self.cfg.max_level_at_mixed

    def _current_R(self) -> float:
        if self._field_R_fn is None:
            # No field bound: treat as locked. Callers that want R-gating
            # supply a field_R_fn that reads the live Kuramoto field.
            return 1.0
        return float(self._field_R_fn())

    # ── fold with φ-weight ──────────────────────────────────────────
    def _fold(self, packet: HierarchicalPacket) -> None:
        """Fold a packet into the stream with φ^(-level) weighting.

        Accumulates without intermediate renormalization. The stream's
        _hv is the raw weighted sum Σ w_k · hv_k; normalization happens
        at readout() only. This makes the fold order-independent: the
        sum is commutative and normalization is a pure function of the
        sum.

        Does not use StreamState.update() because that method
        normalizes per call. SourceIngestor keeps its own accumulation
        policy.
        """
        weight = phi_weight(packet.level)
        s = self.stream
        s._hv = s._hv + weight * packet.hv
        if s._span_start is None:
            s._span_start = int(packet.span_start)
            s._span_end = int(packet.span_end)
        else:
            s._span_start = min(s._span_start, int(packet.span_start))
            s._span_end = max(s._span_end, int(packet.span_end))
        s._count += 1
        s._last_level = int(packet.level)

    # ── ingest ──────────────────────────────────────────────────────
    def ingest(
        self,
        tokens: list[int],
        source_id: str,
        quality_fn: Optional[QualityFn] = None,
        extractor: Optional[ExtractorFn] = None,
    ) -> IngestionResult:
        if source_id in self.cfg.source_blacklist:
            return IngestionResult(
                source_id=source_id,
                packets_emitted=0,
                packets_accepted=0,
                packets_rejected=0,
                facts_written=0,
                field_R_at_ingest=self._current_R(),
                max_level_accepted=0,
                rejection_reasons={"blacklisted": 1},
            )

        q_fn = quality_fn or _default_quality
        R_now = self._current_R()
        max_level = self._max_level_for_R(R_now)

        packets = self.encoder.push_many(list(tokens))
        packets += self.encoder.flush()

        accepted = 0
        rejected = 0
        facts_written = 0
        highest_accepted_level = 0
        reasons: dict[str, int] = {}

        for packet in packets:
            if accepted >= self.cfg.max_per_source:
                reasons["max_per_source"] = (
                    reasons.get("max_per_source", 0) + 1
                )
                rejected += 1
                continue

            if packet.level > max_level:
                reasons["level_above_R_gate"] = (
                    reasons.get("level_above_R_gate", 0) + 1
                )
                rejected += 1
                continue

            r, csi = q_fn(packet, R_now)
            if r < self.cfg.r_min:
                reasons["r_below_min"] = (
                    reasons.get("r_below_min", 0) + 1
                )
                rejected += 1
                continue
            if csi < self.cfg.csi_min:
                reasons["csi_below_min"] = (
                    reasons.get("csi_below_min", 0) + 1
                )
                rejected += 1
                continue

            self._fold(packet)
            accepted += 1
            highest_accepted_level = max(
                highest_accepted_level, packet.level
            )

            if extractor is not None and self.titanos is not None:
                triples = extractor(packet)
                for s, r_, o in triples:
                    try:
                        self.titanos.learn(str(s), str(r_), str(o))
                        facts_written += 1
                    except Exception:
                        pass

        return IngestionResult(
            source_id=source_id,
            packets_emitted=len(packets),
            packets_accepted=accepted,
            packets_rejected=rejected,
            facts_written=facts_written,
            field_R_at_ingest=R_now,
            max_level_accepted=highest_accepted_level,
            rejection_reasons=reasons,
        )

    # ── readout ─────────────────────────────────────────────────────
    def readout(self) -> np.ndarray:
        """Return a unit-norm view of the accumulated state.

        The stream's _hv is the raw weighted sum; this method
        normalizes on read without mutating _hv. Subsequent folds
        accumulate onto the same raw sum.
        """
        return _normalize(self.stream.readout())

    def snapshot(self) -> dict:
        return {
            "stream": self.stream.snapshot(),
            "config": {
                "r_min": self.cfg.r_min,
                "csi_min": self.cfg.csi_min,
                "coherence_min": self.cfg.coherence_min,
                "max_per_source": self.cfg.max_per_source,
                "source_blacklist": list(self.cfg.source_blacklist),
                "max_level_at_locked": self.cfg.max_level_at_locked,
                "max_level_at_mixed": self.cfg.max_level_at_mixed,
                "max_level_at_exploring": self.cfg.max_level_at_exploring,
                "locked_threshold": self.cfg.locked_threshold,
                "exploring_threshold": self.cfg.exploring_threshold,
            },
            "phi_inv": float(PHI_INV),
        }


__all__ = [
    "SourceIngestor",
    "IngestionConfig",
    "IngestionResult",
    "QualityFn",
    "ExtractorFn",
    "phi_weight",
    "PHI_INV",
]
