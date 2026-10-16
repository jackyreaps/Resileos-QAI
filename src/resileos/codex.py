"""φ-phased codex.

Deterministic token and position encoders built on φ-seeded
constant-magnitude phasors. Every code is a unit-norm complex vector of dim
components with per-component magnitude 1/sqrt(dim).

Bind and unbind are exact under these conventions:
    bind(a, b)    = a * b * sqrt(dim)
    unbind(c, b)  = c * conj(b) * sqrt(dim)
    unbind(bind(a, b), b) = a

Row indexing is 0-based and matches token IDs directly:
`codebook[t]` is the phasor for token ID `t`. Row 0 is reserved for
token 0. This removes the +1 shift that previously coupled encoding
and cleanup and made round-trip work only by cancellation.

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

        # 0-based rows: codebook[t] is the phasor for token ID t.
        token_ids = np.arange(0, vocab_size, dtype=np.int64)
        self.codebook = _phi_seeded_phasor(token_ids, self.dim, salt=0)

        # Positions similarly 0-based: _positions[p] is slot p.
        position_ids = np.arange(0, max_positions, dtype=np.int64)
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
    def bundle(codes: Sequence[np.ndarray], dim: int | None = None) -> np.ndarray:
        """Bundling operator. Empty input returns the zero vector.

        If codes is empty and dim is None, a length-1 zero vector is
        returned as a placeholder. Callers that know the target dimension
        should pass it explicitly; PhiPhaseCodex.encode always does.
        """
        if not codes:
            if dim is None:
                return np.zeros(1, dtype=np.complex128)
            return np.zeros(int(dim), dtype=np.complex128)
        s = np.sum(np.stack(codes, axis=0), axis=0)
        n = float(np.linalg.norm(s))
        return s / n if n > 1e-12 else s

    def encode(self, tokens: list[int]) -> np.ndarray:
        """Bundle token codes bound to position slots.

        An empty token list returns the zero hypervector. This is the
        bundling identity and avoids raising on the empty case.
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
        return self.bundle(codes, dim=self.dim)

    def cleanup(self, hv: np.ndarray, position: int) -> Optional[int]:
        """Unbind position and return the nearest token ID (or None).

        Row indexing is 0-based and matches token IDs directly, so the
        argmax is the token ID. No +1 shift.
        """
        if not (0 <= position < self.max_positions):
            raise IndexError(f"position {position} out of range")
        probe = self.unbind(hv, self._positions[position])
        sims = np.real(np.conj(self.codebook) @ probe)
        return int(np.argmax(sims))

    def argmax_coherence(
        self,
        hv: np.ndarray,
        position: int,
        top_k: int = 1,
    ) -> list[tuple[int, float]]:
        """Top-k token IDs by cosine coherence with the token at `position`.

        Signature is (hv, position, top_k=1). The test contract calls
        argmax_coherence(hv, 0, top_k=3), so `position` is required and
        `top_k` is keyword. The position slot is unbound before ranking,
        matching `cleanup`.

        Returns a list of (token_id, similarity) pairs ranked by
        decreasing similarity. Returns an empty list if top_k <= 0.
        """
        if top_k <= 0:
            return []
        if not (0 <= position < self.max_positions):
            raise IndexError(f"position {position} out of range")
        hv = np.asarray(hv)
        if hv.shape != (self.dim,):
            raise ValueError(
                f"hv shape {hv.shape} != (dim,) = ({self.dim},)"
            )
        probe = self.unbind(hv, self._positions[position])
        sims = np.real(np.conj(self.codebook) @ probe)
        k = min(int(top_k), len(sims))
        idx = np.argsort(sims)[::-1][:k]
        return [(int(i), float(sims[i])) for i in idx]
