"""Streaming substrate state (RES-311).

A reducer over the hierarchy encoder's packet stream. Maintains a
single running hypervector `stream_hv` that each emitted packet
updates. This is the persistent context the modulation consumer
(RES-315) reads.

Spec: docs/310-hierarchy/streaming-state.md

Off states (explicit):
    decay = 1.0       no decay; every packet contributes equally. The
                      state is a corpus-wide bundle with capacity
                      C(dim) (RES-313 §3).
    seed              retained for reproducibility of any future
                      stochastic extension. The current update rule is
                      deterministic and does not consume the seed.
                      Setting a different seed produces an identical
                      state from identical input.
    learning          off. The state is a pure reducer. No gradients.
    bidirectional     off. The state is a single hypervector.
                      Recovering an arbitrary token requires a position
                      path, which this state does not carry.
    semantic claim    off. `stream_hv` is a running bundle of packets,
                      not a representation of meaning.
    capacity guarantee off. The state's recall capacity is bounded by
                      RES-313, not by this module. `entropy()` is a
                      diagnostic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .encoder import HierarchicalPacket


def _normalize(hv: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(hv))
    if n < 1e-12:
        return hv.copy()
    return hv / n


@dataclass
class StreamStateConfig:
    """Configuration for a StreamState.

    dim    hypervector dimension. Must match the encoder's codex dim.
    decay  scalar in (0, 1]. Controls the effective horizon.
           decay = 1.0 -> no decay (spec §3).
    seed   reserved for reproducibility. Not consumed by the current
           deterministic update rule.
    """
    dim: int
    decay: float = 1.0
    seed: int = 0

    def __post_init__(self) -> None:
        # Coerce first, then compare. Comparing before coercion raises
        # TypeError on string input instead of the intended ValueError.
        self.dim = int(self.dim)
        self.decay = float(self.decay)
        self.seed = int(self.seed)

        if self.dim < 2:
            raise ValueError("dim must be >= 2")
        if not (0.0 < self.decay <= 1.0):
            raise ValueError("decay must be in (0, 1]")


class StreamState:
    """Running state over a packet stream (RES-311).

    Fields (spec §2):
        stream_hv           complex128[dim]   running bundle
        stream_span         (start, end)      token-index interval
                                              covered
        stream_packet_count int               number of packets folded in
        last_packet_level   int               level of last packet
                                              (0 = none)

    Update rule (spec §3):
        stream_hv = normalize(stream_hv + decay**L_p * hv_p)
        stream_span = (min(start, s_p), max(end, e_p))
        stream_packet_count += 1
        last_packet_level = L_p
    """

    def __init__(self, cfg: StreamStateConfig) -> None:
        if not isinstance(cfg, StreamStateConfig):
            raise TypeError("cfg must be a StreamStateConfig")
        self.cfg = cfg
        self._hv: np.ndarray = np.zeros(cfg.dim, dtype=np.complex128)
        self._span_start: Optional[int] = None
        self._span_end: Optional[int] = None
        self._count: int = 0
        self._last_level: int = 0

    # ── properties ──────────────────────────────────────────────────
    @property
    def dim(self) -> int:
        return self.cfg.dim

    @property
    def decay(self) -> float:
        return self.cfg.decay

    @property
    def packet_count(self) -> int:
        return self._count

    @property
    def span(self) -> tuple[Optional[int], Optional[int]]:
        return (self._span_start, self._span_end)

    @property
    def last_packet_level(self) -> int:
        return self._last_level

    # ── update ──────────────────────────────────────────────────────
    def update(self, packet: HierarchicalPacket) -> None:
        """Fold one packet into the running state (spec §3)."""
        if not isinstance(packet, HierarchicalPacket):
            raise TypeError("packet must be a HierarchicalPacket")
        if packet.hv.shape != (self.cfg.dim,):
            raise ValueError(
                f"packet hv shape {packet.hv.shape} != "
                f"(dim,) = ({self.cfg.dim},)"
            )
        weight = float(self.cfg.decay) ** int(packet.level)
        self._hv = _normalize(self._hv + weight * packet.hv)

        if self._span_start is None:
            self._span_start = int(packet.span_start)
            self._span_end = int(packet.span_end)
        else:
            self._span_start = min(
                self._span_start, int(packet.span_start)
            )
            self._span_end = max(
                self._span_end, int(packet.span_end)
            )

        self._count += 1
        self._last_level = int(packet.level)

    def update_many(self, packets: list[HierarchicalPacket]) -> None:
        for p in packets:
            self.update(p)

    # ── readout ─────────────────────────────────────────────────────
    def readout(self) -> np.ndarray:
        """Return the running hypervector (spec §4)."""
        return self._hv.copy()

    def entropy(self) -> float:
        """Effective number of packets contributing (spec §4).

        For a unit-norm bundle of N random phasors, ||sum||^2 ~ N in
        expectation. This returns ||stream_hv||^2. Diagnostic only.
        """
        return float(np.sum(np.abs(self._hv) ** 2))

    def snapshot(self) -> dict:
        """Full state dict (spec §4)."""
        return {
            "dim": int(self.cfg.dim),
            "decay": float(self.cfg.decay),
            "seed": int(self.cfg.seed),
            "packet_count": int(self._count),
            "span_start": self._span_start,
            "span_end": self._span_end,
            "last_packet_level": int(self._last_level),
            "entropy": self.entropy(),
        }

    # ── persistence ─────────────────────────────────────────────────
    def save(self, path: str | Path) -> None:
        """Serialize to a single .npz file (spec §5)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            p,
            hv=self._hv,
            dim=np.int64(self.cfg.dim),
            decay=np.float64(self.cfg.decay),
            seed=np.int64(self.cfg.seed),
            span_start=np.int64(
                -1 if self._span_start is None else self._span_start
            ),
            span_end=np.int64(
                -1 if self._span_end is None else self._span_end
            ),
            count=np.int64(self._count),
            last_level=np.int64(self._last_level),
        )

    @classmethod
    def load(cls, path: str | Path) -> "StreamState":
        """Reconstruct from a .npz written by save() (spec §5)."""
        raw = np.load(Path(path), allow_pickle=False)
        cfg = StreamStateConfig(
            dim=int(raw["dim"]),
            decay=float(raw["decay"]),
            seed=int(raw["seed"]),
        )
        state = cls(cfg)
        state._hv = raw["hv"].astype(np.complex128)
        s = int(raw["span_start"])
        e = int(raw["span_end"])
        state._span_start = None if s < 0 else s
        state._span_end = None if e < 0 else e
        state._count = int(raw["count"])
        state._last_level = int(raw["last_level"])
        return state

    def reset(self) -> None:
        """Return to initial state: zero vector, empty span, zero count."""
        self._hv = np.zeros(self.cfg.dim, dtype=np.complex128)
        self._span_start = None
        self._span_end = None
        self._count = 0
        self._last_level = 0

    # ── introspection ───────────────────────────────────────────────
    def __repr__(self) -> str:
        s, e = self.span
        return (
            f"StreamState(dim={self.cfg.dim}, decay={self.cfg.decay}, "
            f"count={self._count}, span=({s}, {e}), "
            f"last_level={self._last_level})"
        )


__all__ = ["StreamState", "StreamStateConfig"]
