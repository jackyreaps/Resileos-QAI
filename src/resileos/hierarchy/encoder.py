"""Hierarchical encoder (RES-310).

Cascades buffers, one per level. When a buffer reaches capacity it flushes
as a single bundle bound to that level's position codes, and the resulting
hypervector is appended to the level above. Cascades propagate to the top.

See docs/310-hierarchy/hierarchical-encoding.md for the spec.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..codex import PhiPhaseCodex

_SEED_MULT = 2654435761
_SEED_MOD = 2**31
_LEVEL_SALT = 7919  # prime, distinguishes per-level phasor streams


def default_capacity(dim: int) -> int:
    """C(dim) = floor(dim / (2 ln dim)), floored at 8.

    Below 8 the tree has no meaningful branching factor and the encoder
    should use capacities that reflect the actual recall budget.
    """
    if dim < 4:
        raise ValueError("dim must be >= 4")
    return max(8, int(dim / (2.0 * np.log(dim))))


def level_phasor(indices: np.ndarray, dim: int, level: int) -> np.ndarray:
    """φ-seeded constant-magnitude phasors for one position-code level.

    Different level -> different salt -> statistically independent codes.
    """
    out = np.zeros((len(indices), dim), dtype=np.complex128)
    for i, idx in enumerate(indices):
        seed = (int(idx) * _SEED_MULT + level * _LEVEL_SALT + 17) % _SEED_MOD
        rng = np.random.default_rng(seed)
        phases = rng.uniform(-np.pi, np.pi, size=dim)
        out[i] = np.exp(1j * phases) / np.sqrt(dim)
    return out


@dataclass
class HierarchicalPacket:
    """A closed bundle at some level.

    level:       1 = bundle of tokens, 2 = bundle of level-1 packets, etc.
    hv:          unit-norm complex hypervector of length dim.
    span_start:  first token index covered (inclusive).
    span_end:    last token index covered (exclusive).
    child_count: number of items bundled at the level below.
    """
    level: int
    hv: np.ndarray
    span_start: int
    span_end: int
    child_count: int

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError("packet level must be >= 1")
        if self.span_end < self.span_start:
            raise ValueError("span_end must be >= span_start")
        if self.child_count < 1:
            raise ValueError("child_count must be >= 1")


class HierarchicalEncoder:
    """Streaming hierarchical encoder.

    Parameters
    ----------
    codex : PhiPhaseCodex
        Supplies bind/unbind/bundle and the token codebook.
    capacities : sequence of int, optional
        capacities[L] = number of level-L items per level-(L+1) packet.
        If None, defaults to [C(dim)] * 4.
    """

    def __init__(
        self,
        codex: PhiPhaseCodex,
        capacities: Optional[list[int]] = None,
    ) -> None:
        if capacities is None:
            c = default_capacity(codex.dim)
            capacities = [c, c, c, c]
        if not capacities:
            raise ValueError("capacities must be non-empty")
        if any(c < 2 for c in capacities):
            raise ValueError("each capacity must be >= 2")
        if any(c > codex.max_positions for c in capacities):
            raise ValueError(
                f"capacity exceeds codex.max_positions ({codex.max_positions}); "
                "increase max_positions or reduce capacities"
            )

        self.codex = codex
        self.capacities = list(capacities)
        self.n_levels = len(capacities)

        self.pos_codes = [
            level_phasor(np.arange(0, cap), codex.dim, level)
            for level, cap in enumerate(capacities)
        ]

        self._buffers: list[list[np.ndarray]] = [[] for _ in capacities]
        self._spans: list[list[tuple[int, int]]] = [[] for _ in capacities]
        self.token_count = 0

    # ── public API ─────────────────────────────────────────────────────
    def push(self, token_id: int) -> list[HierarchicalPacket]:
        """Append one token. Return all packets closed by this push."""
        if not (0 <= int(token_id) < self.codex.vocab_size):
            raise ValueError(f"token {token_id} out of vocab range")
        tok_hv = self.codex.phase_code(int(token_id))
        i = self.token_count
        self._buffers[0].append(tok_hv)
        self._spans[0].append((i, i + 1))
        self.token_count += 1
        return self._cascade()

    def push_many(self, tokens: list[int]) -> list[HierarchicalPacket]:
        out: list[HierarchicalPacket] = []
        for t in tokens:
            out.extend(self.push(t))
        return out

    def flush(self) -> list[HierarchicalPacket]:
        """Force-flush all partial buffers bottom-up. Return all packets."""
        out: list[HierarchicalPacket] = []
        for level in range(self.n_levels):
            if not self._buffers[level]:
                continue
            packet = self._flush_level(level)
            out.append(packet)
            if level + 1 < self.n_levels:
                self._buffers[level + 1].append(packet.hv)
                self._spans[level + 1].append(
                    (packet.span_start, packet.span_end)
                )
        # cascaded appends may have filled upper buffers
        out.extend(self._cascade())
        return out

    def reset(self) -> None:
        self._buffers = [[] for _ in self.capacities]
        self._spans = [[] for _ in self.capacities]
        self.token_count = 0

    # ── internals ──────────────────────────────────────────────────────
    def _cascade(self) -> list[HierarchicalPacket]:
        out: list[HierarchicalPacket] = []
        level = 0
        while (
            level < self.n_levels
            and len(self._buffers[level]) >= self.capacities[level]
        ):
            packet = self._flush_level(level)
            out.append(packet)
            if level + 1 < self.n_levels:
                self._buffers[level + 1].append(packet.hv)
                self._spans[level + 1].append(
                    (packet.span_start, packet.span_end)
                )
            level += 1
        return out

    def _flush_level(self, level: int) -> HierarchicalPacket:
        buf = self._buffers[level]
        if not buf:
            raise RuntimeError(f"flush on empty buffer at level {level}")
        pos = self.pos_codes[level]
        bound = [
            self.codex.bind(child, pos[i]) for i, child in enumerate(buf)
        ]
        bundled = self.codex.bundle(bound)
        span_start = self._spans[level][0][0]
        span_end = self._spans[level][-1][1]
        child_count = len(buf)
        self._buffers[level] = []
        self._spans[level] = []
        return HierarchicalPacket(
            level=level + 1,
            hv=bundled,
            span_start=span_start,
            span_end=span_end,
            child_count=child_count,
        )
