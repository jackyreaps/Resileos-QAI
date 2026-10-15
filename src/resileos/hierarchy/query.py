"""Hierarchical query (RES-310).

Top-down retrieval: given a bundle at level L and a target child, find
the position whose unbind best matches. Descent walks a path from a
top-level packet down to a token and cleans up.
"""
from __future__ import annotations

import numpy as np

from .encoder import HierarchicalEncoder, HierarchicalPacket


class HierarchicalQuery:
    def __init__(self, encoder: HierarchicalEncoder) -> None:
        self.encoder = encoder
        self.codex = encoder.codex
        self.pos_codes = encoder.pos_codes
        self.capacities = encoder.capacities
        self.n_levels = encoder.n_levels

    # ── single-level ops ────────────────────────────────────────────
    def locate(
        self,
        bundle_hv: np.ndarray,
        pos_level: int,
        target_hv: np.ndarray,
    ) -> tuple[int, float]:
        """Find the position at `pos_level` whose unbind best matches target.

        pos_level indexes into pos_codes and must be in [0, n_levels).
        Returns (position_index, cosine similarity).
        """
        if not (0 <= pos_level < self.n_levels):
            raise ValueError(f"pos_level {pos_level} out of range")
        codes = self.pos_codes[pos_level]
        n_codes = len(codes)
        best_i, best_sim = -1, -float("inf")
        for i in range(n_codes):
            probe = self.codex.unbind(bundle_hv, codes[i])
            sim = float(np.real(np.vdot(probe, target_hv)))
            if sim > best_sim:
                best_sim = sim
                best_i = i
        return best_i, best_sim

    def retrieve(
        self,
        bundle_hv: np.ndarray,
        pos_level: int,
        position: int,
    ) -> np.ndarray:
        """Recover the child stored at `position` under `pos_level`."""
        if not (0 <= pos_level < self.n_levels):
            raise ValueError(f"pos_level {pos_level} out of range")
        codes = self.pos_codes[pos_level]
        if not (0 <= position < len(codes)):
            raise ValueError(
                f"position {position} out of range at pos_level "
                f"{pos_level} (have {len(codes)})"
            )
        return self.codex.unbind(bundle_hv, codes[position])

    # ── descent ─────────────────────────────────────────────────────
    def descend_to_token(
        self,
        packet: HierarchicalPacket,
        path: list[int],
    ) -> tuple[int, np.ndarray]:
        """Walk a full position path from `packet` down to a token.

        path must have length packet.level. path[0] indexes
        pos_codes[packet.level - 1]; path[-1] indexes pos_codes[0].
        Returns (token_id, raw_token_hv).
        """
        if len(path) != packet.level:
            raise ValueError(
                f"path length {len(path)} != packet.level {packet.level}"
            )
        current = packet.hv
        for depth, pos in enumerate(path):
            pos_level = packet.level - 1 - depth
            current = self.retrieve(current, pos_level, pos)
        token_id = self._cleanup_token(current)
        return token_id, current

    # ── token cleanup ───────────────────────────────────────────────
    def _cleanup_token(self, token_hv: np.ndarray) -> int:
        """Nearest-neighbour token ID for a recovered token hypervector.

        The codex codebook is built from `np.arange(1, vocab_size + 1)`,
        so `codebook[i]` holds the phasor for token ID `i + 1`. The
        argmax index must therefore be shifted by one to recover the
        token ID. Without the shift, cleanup returns an index in
        [0, vocab_size) that is off by one from every true token ID.
        """
        sims = np.real(np.conj(self.codex.codebook) @ token_hv)
        return int(np.argmax(sims)) + 1
