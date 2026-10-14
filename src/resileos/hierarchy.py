"""Hierarchical encoding (RES-310).

Multi-level VSA bundles that let a fixed-dimension substrate carry token
sequences longer than a single bundle can hold. Each level binds its children
to position phasors unique to that level, then bundles. The result is a tree
of hypervectors whose leaves are tokens and whose root is a level-N packet.

Level numbering:
    buffer[0]  holds token codes;     bundling produces level-1 packets
    buffer[k]  holds level-k packets; bundling produces level-(k+1) packets

A packet at level L has `child_count` children, each bound to a position
phasor at level L-1. To descend, unbind with those same phasors.

Capacity per level defaults to dim / (2 log dim), the standard VSA bundle
capacity bound. Callers override per level via `capacities`.

Orientation (RES-307): the level index is baked into the phasor seed, so
position codes at different levels are near-orthogonal. That prevents a
level-1 position from aliasing with a level-2 position at the same index,
which is what makes clean descent possible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np


# ── capacity ────────────────────────────────────────────────────────────
def default_capacity(dim: int) -> int:
    """Standard VSA bundle capacity: dim / (2 log dim).

    For dim=512 this returns 41, for dim=1024 it returns 73. Both are well
    within the ranges the tests exercise, and the function is monotone in dim.
    """
    if dim < 4:
        raise ValueError("dim must be >= 4")
    return max(2, int(dim / (2.0 * np.log(dim))))


# ── level phasors ───────────────────────────────────────────────────────
_POS_MULT = 2654435761
_LVL_MULT = 40503
_SALT = 0x9E3779B9  # φ-ish offset so seeds don't collide at (0,0)
_SEED_MOD = 2**31


def _seed_for(position: int, level: int) -> int:
    return (int(position) * _POS_MULT + int(level) * _LVL_MULT + _SALT) % _SEED_MOD


def level_phasor(
    positions: Sequence[int] | np.ndarray,
    dim: int,
    level: int,
) -> np.ndarray:
    """Unit-norm complex phasors for the given positions at the given level.

    Row i has norm 1 (each component has magnitude 1/sqrt(dim)). Phasors at
    different levels are near-orthogonal because the level index is folded
    into the per-row seed.
    """
    positions = list(positions)
    out = np.zeros((len(positions), dim), dtype=np.complex128)
    inv_sqrt_d = 1.0 / np.sqrt(dim)
    for i, p in enumerate(positions):
        seed = _seed_for(int(p), int(level))
        rng = np.random.default_rng(seed)
        phases = rng.uniform(-np.pi, np.pi, size=dim)
        out[i] = np.exp(1j * phases) * inv_sqrt_d
    return out


# ── packet ──────────────────────────────────────────────────────────────
@dataclass
class HierarchicalPacket:
    hv: np.ndarray
    level: int
    child_count: int
    span_start: int
    span_end: int


# ── encoder ─────────────────────────────────────────────────────────────
class HierarchicalEncoder:
    """Stream tokens; emit packets at each level as buffers fill.

    Each buffer entry is (hv, span_start, span_end). Spans are always in
    token units, so a packet's span_start/span_end describe the token range
    it covers regardless of how deep the packet sits.
    """

    def __init__(self, codex, capacities: Iterable[int]) -> None:
        self.codex = codex
        self.capacities = [int(c) for c in capacities]
        if any(c < 1 for c in self.capacities):
            raise ValueError("capacities must all be >= 1")
        self.buffers: list[list[tuple[np.ndarray, int, int]]] = [
            [] for _ in self.capacities
        ]
        self._token_count = 0

    @property
    def token_count(self) -> int:
        return self._token_count

    def reset(self) -> None:
        self._token_count = 0
        for b in self.buffers:
            b.clear()

    # ── push ────────────────────────────────────────────────────────
    def push(self, token: int) -> Optional[HierarchicalPacket]:
        t = int(token)
        if not (0 <= t < self.codex.vocab_size):
            raise ValueError(f"token {t} out of vocab")
        start = self._token_count
        end = start + 1
        self._token_count = end
        token_hv = self.codex.codebook[t].copy()
        self.buffers[0].append((token_hv, start, end))
        return self._cascade()

    def push_many(self, tokens: Iterable[int]) -> list[HierarchicalPacket]:
        out: list[HierarchicalPacket] = []
        for t in tokens:
            p = self.push(t)
            if p is not None:
                out.append(p)
        return out

    def _cascade(self) -> Optional[HierarchicalPacket]:
        """Bundle any buffers that have reached capacity, bottom-up.

        Returns the highest-level packet produced by this cascade, or None
        if no buffer filled. Buffers already at capacity when the cascade
        reaches them (from a previous push) are also bundled.
        """
        top: Optional[HierarchicalPacket] = None
        for k in range(len(self.capacities)):
            if len(self.buffers[k]) < self.capacities[k]:
                break
            p = self._bundle_buffer(k)
            if p is not None:
                top = p
        return top

    def _bundle_buffer(self, k: int) -> Optional[HierarchicalPacket]:
        """Bundle the current contents of buffer[k] into a level-(k+1) packet."""
        children = self.buffers[k]
        if not children:
            return None
        n = len(children)
        positions = list(range(1, n + 1))
        codes = level_phasor(positions, self.codex.dim, level=k)
        bound = [
            self.codex.bind(children[i][0], codes[i]) for i in range(n)
        ]
        bundled = self.codex.bundle(bound)
        span_start = children[0][1]
        span_end = children[-1][2]
        packet = HierarchicalPacket(
            hv=bundled,
            level=k + 1,
            child_count=n,
            span_start=span_start,
            span_end=span_end,
        )
        self.buffers[k] = []
        if k + 1 < len(self.capacities):
            self.buffers[k + 1].append((bundled, span_start, span_end))
        return packet

    # ── flush ───────────────────────────────────────────────────────
    def flush(self) -> Optional[HierarchicalPacket]:
        """Flush all partial buffers bottom-up. Returns the topmost packet.

        After flush, all buffers are empty. Returns None if nothing to flush.
        """
        if self._token_count == 0:
            return None
        top: Optional[HierarchicalPacket] = None
        for k in range(len(self.capacities)):
            if not self.buffers[k]:
                break
            p = self._bundle_buffer(k)
            if p is not None:
                top = p
        return top


# ── query ───────────────────────────────────────────────────────────────
class HierarchicalQuery:
    """Descent and position lookup over an encoder's hierarchy.

    All methods are read-only. The encoder's codex is used for position
    phasors and for token cleanup.
    """

    def __init__(self, encoder: HierarchicalEncoder) -> None:
        self.enc = encoder
        self.codex = encoder.codex

    def _level_size(self, level: int) -> int:
        if not (0 <= level < len(self.enc.capacities)):
            raise ValueError(f"level {level} out of range")
        return self.enc.capacities[level]

    def retrieve(self, hv: np.ndarray, level: int, position: int) -> np.ndarray:
        """Unbind the position phasor at the given level from a packet hv.

        Returns the child hypervector (or token code if level == 0).
        """
        size = self._level_size(level)
        if not (0 <= position < size):
            raise ValueError(f"position {position} out of range for level {level}")
        code = level_phasor([position + 1], self.codex.dim, level=level)[0]
        return self.codex.unbind(hv, code)

    def locate(
        self, hv: np.ndarray, level: int, target_hv: np.ndarray
    ) -> tuple[int, float]:
        """Find which position at `level` best explains target_hv."""
        size = self._level_size(level)
        best_pos, best_sim = -1, -np.inf
        for p in range(size):
            code = level_phasor([p + 1], self.codex.dim, level=level)[0]
            probe = self.codex.unbind(hv, code)
            sim = float(np.real(np.sum(np.conj(probe) * target_hv)))
            if sim > best_sim:
                best_sim, best_pos = sim, p
        return best_pos, best_sim

    def descend_to_token(
        self, hv: np.ndarray, path: Sequence[int]
    ) -> tuple[int, float]:
        """Follow a path of positions down to a token; return (token_id, sim).

        Path length must equal the number of levels in the encoder.
        At each step, unbind using the level corresponding to that depth.
        """
        n_levels = len(self.enc.capacities)
        if len(path) != n_levels:
            raise ValueError(
                f"path length {len(path)} must equal number of levels {n_levels}"
            )
        current = hv
        for depth, pos in enumerate(path):
            level = n_levels - 1 - depth
            size = self._level_size(level)
            if not (0 <= int(pos) < size):
                raise ValueError(
                    f"position {pos} out of range for level {level}"
                )
            code = level_phasor([int(pos) + 1], self.codex.dim, level=level)[0]
            current = self.codex.unbind(current, code)
        sims = np.real(np.conj(self.codex.codebook) @ current)
        best = int(np.argmax(sims))
        return best, float(sims[best])


__all__ = [
    "HierarchicalEncoder",
    "HierarchicalPacket",
    "HierarchicalQuery",
    "default_capacity",
    "level_phasor",
]
