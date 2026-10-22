"""Kanerva sparse distributed memory + Modern Hopfield relaxation (RES-317).

Mitigates hypervector crosstalk during multi-step VSA unrolling. Two
parameter-free layers in sequence:

    noisy query
        │
        ▼
    Kanerva SDM read      — k-nearest hard locations, contents summed
        │                    Averages over the query's sparse neighborhood.
        ▼                    Reduces per-component noise before the snap.
    Hopfield relaxation   — softmax attention over stored patterns
        │                    (Ramsauer et al. 2020). Snaps to the nearest
        ▼                    stored pattern deterministically.
    clean vector

No trainable parameters. The SDM addresses are fixed at construction
(seeded RNG). The Hopfield patterns are whatever was stored. Update rules
are closed-form.

Off states (explicit):
    learning           off. No gradients. Addresses are seeded; contents
                       and patterns are the write history.
    capacity claim     off. SDM capacity is bounded by n_locations and the
                       k-nearest activation; it does not extend the
                       substrate's flat-bundle capacity (RES-313).
    substitute for     off. This does not replace codex cleanup; it
    codex cleanup      sits in front of it. The final token-level
                       argmax is still against the codebook.
    approximation      off. For clean inputs the pipeline is idempotent
                       (Hopfield relaxation does not move a stored
                       pattern). For noisy inputs it is a projection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class SDMConfig:
    """Kanerva SDM configuration.

    dim             hypervector dimension
    n_locations     number of hard locations (typically 10-100x dim)
    k_activate      how many hard locations activate per read/write
    seed            RNG for the fixed address matrix
    """
    dim: int
    n_locations: int = 1024
    k_activate: int = 32
    seed: int = 0

    def __post_init__(self) -> None:
        self.dim = int(self.dim)
        self.n_locations = int(self.n_locations)
        self.k_activate = int(self.k_activate)
        self.seed = int(self.seed)
        if self.dim < 2:
            raise ValueError("dim must be >= 2")
        if self.n_locations < 1:
            raise ValueError("n_locations must be >= 1")
        if not (1 <= self.k_activate <= self.n_locations):
            raise ValueError(
                "k_activate must be in [1, n_locations]"
            )


@dataclass
class HopfieldConfig:
    """Modern Hopfield configuration (Ramsauer 2020).

    beta        inverse temperature; higher = sharper snap
    max_iters   upper bound on relaxation iterations
    tol         convergence threshold on ||x_new - x||
    """
    beta: float = 8.0
    max_iters: int = 8
    tol: float = 1e-4

    def __post_init__(self) -> None:
        self.beta = float(self.beta)
        self.max_iters = int(self.max_iters)
        self.tol = float(self.tol)
        if self.beta <= 0:
            raise ValueError("beta must be > 0")
        if self.max_iters < 1:
            raise ValueError("max_iters must be >= 1")
        if self.tol <= 0:
            raise ValueError("tol must be > 0")


# ── Kanerva SDM ─────────────────────────────────────────────────────────
class KanervaSDM:
    """Sparse distributed memory with fixed random hard locations.

    Addresses are bipolar (each component is ±1). Write distributes a
    pattern to the contents of the k nearest hard locations. Read sums
    those contents and re-binarises.
    """

    def __init__(self, cfg: SDMConfig) -> None:
        self.cfg = cfg
        rng = np.random.default_rng(cfg.seed)
        self.addresses = rng.choice(
            [-1.0, 1.0], size=(cfg.n_locations, cfg.dim)
        )
        self.contents = np.zeros(
            (cfg.n_locations, cfg.dim), dtype=np.float64
        )
        self._n_writes = 0

    def _activate(self, query: np.ndarray) -> np.ndarray:
        """Indices of the k hard locations nearest to `query`."""
        sims = (self.addresses @ query) / self.cfg.dim
        k = self.cfg.k_activate
        # argpartition for O(n) top-k; -k: gives the k largest
        idx = np.argpartition(sims, -k)[-k:]
        return idx

    def write(self, vector: np.ndarray) -> None:
        """Distribute a pattern to the k nearest hard locations."""
        v = np.asarray(vector, dtype=np.float64)
        if v.shape != (self.cfg.dim,):
            raise ValueError(
                f"vector shape {v.shape} != ({self.cfg.dim},)"
            )
        idx = self._activate(v)
        self.contents[idx] += v
        self._n_writes += 1

    def read(self, query: np.ndarray) -> np.ndarray:
        """Sum the k nearest contents and re-binarise to ±1."""
        q = np.asarray(query, dtype=np.float64)
        if q.shape != (self.cfg.dim,):
            raise ValueError(
                f"query shape {q.shape} != ({self.cfg.dim},)"
            )
        idx = self._activate(q)
        summed = self.contents[idx].sum(axis=0)
        return np.where(summed >= 0.0, 1.0, -1.0)

    @property
    def n_writes(self) -> int:
        return self._n_writes


# ── Modern Hopfield ─────────────────────────────────────────────────────
class ModernHopfield:
    """Continuous Hopfield via softmax attention (Ramsauer 2020).

    Update rule: x <- X^T · softmax(beta · X · x / dim), where X is the
    (n_patterns, dim) matrix of stored patterns. Converges to a fixed
    point; for a clean stored pattern the fixed point is the pattern
    itself (idempotent).
    """

    def __init__(self, cfg: HopfieldConfig) -> None:
        self.cfg = cfg
        self._patterns: Optional[np.ndarray] = None

    def store(self, patterns: np.ndarray) -> None:
        """Replace the stored pattern matrix. Shape (n_patterns, dim)."""
        arr = np.asarray(patterns, dtype=np.float64)
        if arr.ndim != 2:
            raise ValueError(
                f"patterns must be 2-D (n, dim), got shape {arr.shape}"
            )
        self._patterns = arr

    @property
    def n_patterns(self) -> int:
        return 0 if self._patterns is None else self._patterns.shape[0]

    def relax(self, query: np.ndarray) -> np.ndarray:
        """Iterate the Hopfield update from `query` until convergence."""
        if self._patterns is None or self._patterns.shape[0] == 0:
            return np.asarray(query, dtype=np.float64).copy()
        dim = self._patterns.shape[1]
        x = np.asarray(query, dtype=np.float64).copy()
        if x.shape != (dim,):
            raise ValueError(
                f"query shape {x.shape} != ({dim},)"
            )
        beta = self.cfg.beta
        for _ in range(self.cfg.max_iters):
            sims = (self._patterns @ x) / dim
            # numerically stable softmax
            w = np.exp(beta * (sims - sims.max()))
            w = w / (w.sum() + 1e-30)
            x_new = w @ self._patterns
            if np.linalg.norm(x_new - x) < self.cfg.tol:
                return x_new
            x = x_new
        return x


# ── combined pipeline ───────────────────────────────────────────────────
class AttractorMemory:
    """SDM + Hopfield pipeline for VSA crosstalk reduction.

    Stores fact vectors (or any pattern set). On cleanup, the noisy query
    is (a) SDM-read for neighborhood averaging, then (b) Hopfield-relaxed
    to snap to the nearest stored pattern.

    Parameters
    ----------
    sdm_cfg : SDMConfig, required
    hopfield_cfg : HopfieldConfig, optional (defaults)
    """

    def __init__(
        self,
        sdm_cfg: SDMConfig,
        hopfield_cfg: Optional[HopfieldConfig] = None,
    ) -> None:
        self.sdm = KanervaSDM(sdm_cfg)
        self.hopfield = ModernHopfield(
            hopfield_cfg or HopfieldConfig()
        )
        self._patterns: list[np.ndarray] = []

    def store(self, vector: np.ndarray) -> None:
        v = np.asarray(vector, dtype=np.float64)
        if v.shape != (self.sdm.cfg.dim,):
            raise ValueError(
                f"vector shape {v.shape} != ({self.sdm.cfg.dim},)"
            )
        self.sdm.write(v)
        self._patterns.append(v.copy())
        self.hopfield.store(np.stack(self._patterns, axis=0))

    def store_many(self, vectors: np.ndarray) -> None:
        for v in np.asarray(vectors, dtype=np.float64):
            self.store(v)

    def cleanup(self, query: np.ndarray) -> np.ndarray:
        """Two-stage denoise: SDM read, then Hopfield relax."""
        q = np.asarray(query, dtype=np.float64)
        rough = self.sdm.read(q)
        return self.hopfield.relax(rough)

    @property
    def n_patterns(self) -> int:
        return len(self._patterns)

    def snapshot(self) -> dict:
        return {
            "dim": int(self.sdm.cfg.dim),
            "n_locations": int(self.sdm.cfg.n_locations),
            "k_activate": int(self.sdm.cfg.k_activate),
            "n_patterns": int(self.n_patterns),
            "n_writes": int(self.sdm.n_writes),
            "beta": float(self.hopfield.cfg.beta),
            "max_iters": int(self.hopfield.cfg.max_iters),
        }


__all__ = [
    "SDMConfig",
    "HopfieldConfig",
    "KanervaSDM",
    "ModernHopfield",
    "AttractorMemory",
]
