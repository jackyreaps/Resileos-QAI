"""φ-phased codex.

Deterministic token and position encoders built on φ-seeded
constant-magnitude phasors. Every code is a unit-norm complex vector of dim
components with per-component magnitude 1/sqrt(dim).

token t:    phase[d] = 2π · frac(φ · (t+1) · (d+1))
position p: phase[d] = 2π · frac(φ² · (p+1) · (d+1))

Bind and unbind are exact under these conventions:
    bind(a, b)    = a * b * sqrt(dim)
    unbind(c, b)  = c * conj(b) * sqrt(dim)
    unbind(bind(a, b), b) = a

BandCarriers is NOT used here. Its carriers are pure single-frequency Fourier
modes; under element-wise bind two carriers can sum to another carrier's
frequency, which aliases multi-token cleanup. φ-seeded hash phasors do not alias
because adjacent token codes have no additive structure.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

PHI = (1.0 + np.sqrt(5.0)) / 2.0
PHI2 = PHI * PHI
MAX_POSITIONS_DEFAULT = 512


def _phi_phasor(ids: np.ndarray, dim: int, multiplier: float) -> np.ndarray:
    """Return a (len(ids), dim) matrix of unit-norm φ-seeded phasors."""
    ids = np.asarray(ids, dtype=np.float64)
    d = np.arange(1, dim + 1, dtype=np.float64)
    phases = 2.0 * np.pi * np.mod(multiplier * ids[:, None] * d[None, :], 1.0)
    return np.exp(1j * phases) / np.sqrt(dim)


class PhiPhaseCodex:
    def __init__(
        self,
        vocab_size: int,
        dim: int,
        max_positions: int = MAX_POSITIONS_DEFAULT,
    ) -> None:
        if vocab_size < 1:
            raise ValueError("vocab_size must be >= 1")
        if dim < 2:
            raise ValueError("dim must be >= 2")
        if max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        self.vocab_size = int(vocab_size)
        self.dim = int(dim)
        self.max_positions = int(max_positions)
        self._scale = float(np.sqrt(self.dim))

        token_ids = np.arange(1, vocab_size + 1, dtype=np.float64)
        self.codebook = _phi_phasor(token_ids, self.dim, multiplier=PHI)

        position_ids = np.arange(1, max_positions + 1, dtype=np.float64)
        self._positions = _phi_phasor(position_ids, self.dim, multiplier=PHI2)

    def phase_code(self, token_id: int) -> np.ndarray:
        if not (0 <= token_id < self.vocab_size):
            raise IndexError(f"token_id {token_id} out of range")
        return self.codebook[token_id].copy()

    def phase_slot(self, position: int) -> np.ndarray:
        if not (0 <= position < self.max_positions):
            raise IndexError(f"position {position} out of range")
        return self._positions[position].copy()

    def bind(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return a * b * self._scale

    def unbind(self, c: np.ndarray, b: np.ndarray) -> np.ndarray:
        return c * np.conj(b) * self._scale

    @staticmethod
    def bundle(codes: Sequence[np.ndarray]) -> np.ndarray:
        if not codes:
            return np.zeros(1, dtype=np.complex128)
        s = np.sum(np.stack(codes, axis=0), axis=0)
        n = float(np.linalg.norm(s))
        return s / n if n > 1e-12 else s
