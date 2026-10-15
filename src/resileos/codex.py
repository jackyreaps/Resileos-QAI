"""φ-phased codex.

Deterministic token and position encoders built on φ-seeded
constant-magnitude phasors. Every code is a unit-norm complex vector of dim
components with per-component magnitude 1/sqrt(dim).

Bind and unbind are exact under these conventions:
    bind(a, b)    = a * b * sqrt(dim)
    unbind(c, b)  = c * conj(b) * sqrt(dim)
    unbind(bind(a, b), b) = a

The multiplicative φ·id·d schedule aliases under element-wise bind —
adjacent token codes have additive structure in phase. This implementation
uses φ-seeded random phasors instead: each token ID hashes to a unique RNG
seed, which produces incommensurate phase patterns with no additive
structure.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

PHI = (1.0 + np.sqrt(5.0)) / 2.0
MAX_POSITIONS_DEFAULT = 512
_SEED_MULT = 2654435761  # Knuth multiplicative hash
_SEED_MOD = 2**31


def _phi_seeded_phasor(ids: np.ndarray, dim: int, salt: int = 0) -> np.ndarray:
    """Deterministic random phasors, seeded per ID via φ-hash."""
    out = np.zeros((len(ids), dim), dtype=np.complex128)
    for i, tid in enumerate(ids):
        seed = (int(tid) * _SEED_MULT + salt) % _SEED_MOD
        rng = np.random.default_rng(seed)
        phases = rng.uniform(-np.pi, np.pi, size=dim)
        out[i] = np.exp(1j * phases) / np.sqrt(dim)
    return out


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

        token_ids = np.arange(1, vocab_size + 1, dtype=np.int64)
        self.codebook = _phi_seeded_phasor(token_ids, self.dim, salt=0)

        position_ids = np.arange(1, max_positions + 1, dtype=np.int64)
        self._positions = _phi_seeded_phasor(position_ids, self.dim, salt=1)

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
            raise ValueError("codes must be non-empty")
        s = np.sum(np.stack(codes, axis=0), axis=0)
        n = float(np.linalg.norm(s))
        return s / n if n > 1e-12 else s

    def encode(self, tokens: list[int]) -> np.ndarray:
        """Bundle token codes bound to position slots.

        An empty token list returns the zero hypervector. This is the
        bundling identity and avoids raising on the empty case, which
        callers can hit when a stream has no tokens to emit yet.
        """
        if len(tokens) > self.max_positions:
            raise ValueError(
                f"sequence length {len(tokens)} > max_positions "
                f"{self.max_positions}"
            )
        if not tokens:
            return np.zeros(self.dim, dtype=np.complex128)
        codes = []
        for p, t in enumerate(tokens):
            t = int(t)
            if not (0 <= t < self.vocab_size):
                raise ValueError(f"token {t} out of vocab range")
            codes.append(self.bind(self.codebook[t], self._positions[p]))
        return self.bundle(codes)

    def cleanup(self, hv: np.ndarray, position: int) -> Optional[int]:
        """Unbind position and return the nearest token ID (or None).

        The codebook is built from `np.arange(1, vocab_size + 1)`, so
        `codebook[i]` holds the phasor for token ID `i + 1`. The argmax
        index must be shifted by one to recover the token ID.
        """
        if not (0 <= position < self.max_positions):
            raise IndexError(f"position {position} out of range")
        probe = self.unbind(hv, self._positions[position])
        sims = np.real(np.conj(self.codebook) @ probe)
        best = int(np.argmax(sims))
        return best + 1

    def argmax_coherence(
        self, hv: np.ndarray, k: int = 1
    ) -> list[int]:
        """Top-k token IDs by cosine coherence with a query hypervector.

        The codebook is built from `np.arange(1, vocab_size + 1)`, so
        `codebook[i]` holds the phasor for token ID `i + 1`. The argmax
        index must be shifted by one to recover token IDs.

        Returns a list of token IDs, ranked by decreasing coherence.
        Returns an empty list if k <= 0.
        """
        if k <= 0:
            return []
        sims = np.real(np.conj(self.codebook) @ hv)
        if k == 1:
            return [int(np.argmax(sims)) + 1]
        k = min(int(k), len(sims))
        idx = np.argsort(sims)[::-1][:k]
        return [int(i) + 1 for i in idx]
