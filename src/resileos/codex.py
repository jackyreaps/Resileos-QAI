"""
φ-phased codex.

Maps a token_id to a phase code and a position to a phase slot using
BandCarriers (phasor.py) for the golden-Weil schedule already in the
repo. One BandCarriers instance is used with disjoint index ranges so
token codes and position codes never coincide for the same index.

    token code:    band 1 + token_id
    position code: band (vocab_size + 1) + position

Encode is bind(slot) then bundle. Decode is unbind(slot) then argmax
coherence. Cleanup is decode with top_k = 1.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from .substrate.phasor import BandCarriers


MAX_POSITIONS_DEFAULT = 512


class PhiPhaseCodex:

    def __init__(self, vocab_size: int, dim: int,
                 max_positions: int = MAX_POSITIONS_DEFAULT) -> None:
        if vocab_size < 1:
            raise ValueError("vocab_size must be >= 1")
        if dim < 2:
            raise ValueError("dim must be >= 2")
        if max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        self.vocab_size = int(vocab_size)
        self.dim = int(dim)
        self.max_positions = int(max_positions)

        total_bands = vocab_size + max_positions + 2
        self._bands = BandCarriers(dim=self.dim, n_bands=total_bands)
        self._token_base = 1
        self._position_base = vocab_size + 1

        self.codebook = np.stack(
            [self._bands.carrier(self._token_base + t)
             for t in range(vocab_size)],
            axis=0,
        )

    def phase_code(self, token_id: int) -> np.ndarray:
        if not (0 <= token_id < self.vocab_size):
            raise IndexError(f"token_id {token_id} out of range")
        return self.codebook[token_id].copy()

    def phase_slot(self, position: int) -> np.ndarray:
        if not (0 <= position < self.max_positions):
            raise IndexError(f"position {position} out of range")
        return self._bands.carrier(self._position_base + position)

    @staticmethod
    def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return a * b

    @staticmethod
    def unbind(c: np.ndarray, b: np.ndarray) -> np.ndarray:
        return c * np.conj(b)

    @staticmethod
    def bundle(codes: Sequence[np.ndarray]) -> np.ndarray:
        if not codes:
            return np.zeros(1, dtype=np.complex128)
        s = np.sum(np.stack(codes, axis=0), axis=0)
        n = float(np.linalg.norm(s))
        return s / n if n > 1e-12 else s

    def encode(self, tokens: Sequence[int]) -> np.ndarray:
        if len(tokens) == 0:
            return np.zeros(self.dim, dtype=np.complex128)
        if len(tokens) > self.max_positions:
            raise ValueError(
                f"sequence length {len(tokens)} > max_positions "
                f"{self.max_positions}")
        codes = [self.bind(self.phase_code(int(t)), self.phase_slot(p))
                 for p, t in enumerate(tokens)]
        return self.bundle(codes)

    def argmax_coherence(self, hv: np.ndarray, position: int,
                         top_k: Optional[int] = None
                         ) -> list[tuple[int, float]]:
        hv = np.asarray(hv, dtype=np.complex128)
        if hv.shape != (self.dim,):
            raise ValueError(f"hv shape {hv.shape} != ({self.dim},)")
        unbound = self.unbind(hv, self.phase_slot(position))
        norm = float(np.linalg.norm(unbound)) + 1e-12
        coherence = np.real(self.codebook @ np.conj(unbound)) / norm
        if top_k is None:
            top_k = self.vocab_size
        order = np.argsort(-coherence)[:top_k]
        return [(int(t), float(coherence[t])) for t in order]

    def cleanup(self, hv: np.ndarray, position: int) -> Optional[int]:
        ranked = self.argmax_coherence(hv, position, top_k=1)
        return ranked[0][0] if ranked else None


__all__ = ["PhiPhaseCodex", "MAX_POSITIONS_DEFAULT"]
