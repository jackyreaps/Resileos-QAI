"""
φ-phased codex.

Maps a token_id to a phase code and a position to a phase slot using
BandCarriers (phasor.py) for the golden-Weil schedule already in the
repo. Encode is bind(slot) then bundle. Decode is unbind(slot) then
argmax coherence. Cleanup is decode with top_k = 1.

Band 0 of each BandCarriers is degenerate (ω_0 = 0), so indices are
shifted by +1.
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

        self._token_bands = BandCarriers(dim=self.dim,
                                         n_bands=vocab_size + 1)
        self._position_bands = BandCarriers(dim=self.dim,
                                            n_bands=max_positions + 1)
        self.codebook = np.stack(
            [self._token_bands.carrier(t + 1) for t in range(vocab_size)],
            axis=0,
        )

    def phase_code(self, token_id: int) -> np.ndarray:
        if not (0 <= token_id < self.vocab_size):
            raise IndexError(f"token_id {token_id} out of range")
        return self.codebook[token_id].copy()

    def phase_slot(self, position: int) -> np.ndarray:
        if not (0 <= position < self.max_positions):
            raise IndexError(f"position {position} out of range")
        return self._position_bands.carrier(position + 1)

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
        coherence = np.real(self.codebook @ np.conj(unbound)) / float(self.dim)
        if top_k is None:
            top_k = self.vocab_size
        order = np.argsort(-coherence)[:top_k]
        return [(int(t), float(coherence[t])) for t in order]

    def cleanup(self, hv: np.ndarray, position: int) -> Optional[int]:
        ranked = self.argmax_coherence(hv, position, top_k=1)
        return ranked[0][0] if ranked else None


__all__ = ["PhiPhaseCodex", "MAX_POSITIONS_DEFAULT"]
