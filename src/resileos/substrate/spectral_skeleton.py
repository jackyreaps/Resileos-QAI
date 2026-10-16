"""Spectral skeleton (RES-607).

Discrete combinatorial data that determines D_res. The skeleton exposes
the eigenvalues and multiplicities of the residual Dirac operator as
functions of the discrete ladders already present in the substrate:

    - ε-ladder:  RES-200 residual grid, ε = 1/64
    - golden ladder:  KuramotoField ω values (golden_powers)
    - prime tower:  RES-312 Cipolla-normalised primes
    - primorial Nyquist bound:  RES-312 extension
    - rank folds:  φ-compress contraction levels
    - mask-stack weights:  RES-312 layer schedule 1/(l+1)

No continuous parameters. Every entry is either read from an existing
constant or computed from one of the ladders above.

The composition rule for `cascade()` is a design choice, not a
derivation. Two composition strategies are provided:

    "golden_x_prime"          eigenvalues = golden × prime, mult = 1
    "golden_with_prime_mult"  eigenvalues = golden, mult = prime

Off states (explicit):
    metric claim         off. The skeleton produces a spectrum, not a
                         metric. The spectrum-to-g_ij bridge is a
                         separate consumer.
    uniqueness claim     off. The composition rule is a design choice.
    physics claim        off. "Spectral" is used in the mathematical
                         sense.
    Connes conditions    off. Not a strict spectral triple. This is
                         its discrete input.
    frozen-core          off. Reads PrimeTower and codex constants.
                         Writes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..codex import PHI
from .prime_tower import PrimeTower


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class SpectralSkeletonConfig:
    """Discrete ladders that determine D_res.

    epsilon        residual grid quantum (RES-200)
    n_golden       number of golden-ladder levels
    omega_base     base frequency for the golden ladder
    tower_max_level  highest prime tower level to read
    composition    cascade strategy (see module docstring)
    seed           reserved. Not consumed.
    """
    epsilon: float = 1.0 / 64.0
    n_golden: int = 8
    omega_base: float = 2.0 * np.pi
    tower_max_level: int = 16
    composition: str = "golden_x_prime"
    seed: int = 0

    def __post_init__(self) -> None:
        self.epsilon = float(self.epsilon)
        self.n_golden = int(self.n_golden)
        self.omega_base = float(self.omega_base)
        self.tower_max_level = int(self.tower_max_level)
        self.seed = int(self.seed)

        if self.epsilon <= 0.0:
            raise ValueError("epsilon must be > 0")
        if self.n_golden < 1:
            raise ValueError("n_golden must be >= 1")
        if self.tower_max_level < 2:
            raise ValueError("tower_max_level must be >= 2")
        if self.composition not in (
            "golden_x_prime",
            "golden_with_prime_mult",
        ):
            raise ValueError(f"unknown composition: {self.composition!r}")


# ── output ──────────────────────────────────────────────────────────────
@dataclass
class SkeletonSpectrum:
    """Eigenvalues and multiplicities of D_res from the skeleton.

    eigenvalues      (n,) float64, non-negative
    multiplicities   (n,) int64, >= 1
    """
    eigenvalues: np.ndarray
    multiplicities: np.ndarray

    def __post_init__(self) -> None:
        self.eigenvalues = np.asarray(self.eigenvalues, dtype=np.float64)
        self.multiplicities = np.asarray(self.multiplicities, dtype=np.int64)
        if self.eigenvalues.shape != self.multiplicities.shape:
            raise ValueError(
                f"eigenvalues shape {self.eigenvalues.shape} != "
                f"multiplicities shape {self.multiplicities.shape}"
            )
        if self.eigenvalues.ndim != 1:
            raise ValueError("eigenvalues must be 1-D")
        if np.any(self.multiplicities < 1):
            raise ValueError("multiplicities must all be >= 1")

    @property
    def n_eigenvalues(self) -> int:
        return int(self.eigenvalues.size)

    @property
    def trace(self) -> float:
        """Σ λ_i · m_i. The unnormalised spectral action at zeroth order."""
        return float(np.sum(self.eigenvalues * self.multiplicities))

    @property
    def highest_mode(self) -> float:
        """Largest eigenvalue. The natural UV cutoff of the skeleton."""
        return float(np.max(self.eigenvalues))

    def to_dict(self) -> dict:
        return {
            "eigenvalues": self.eigenvalues.tolist(),
            "multiplicities": self.multiplicities.tolist(),
            "n_eigenvalues": self.n_eigenvalues,
            "trace": self.trace,
            "highest_mode": self.highest_mode,
            "composition": None,  # populated by the parent skeleton
        }


# ── skeleton ────────────────────────────────────────────────────────────
class SpectralSkeleton:
    """Discrete combinatorial data for D_res.

    Construction:
        skel = SpectralSkeleton(SpectralSkeletonConfig(n_golden=8))
        spectrum = skel.cascade()
        spectrum.eigenvalues      # (8,) float64
        spectrum.multiplicities   # (8,) int64

    All ladders are computed once and cached.
    """

    def __init__(self, cfg: Optional[SpectralSkeletonConfig] = None) -> None:
        self.cfg = cfg or SpectralSkeletonConfig()
        self._tower: Optional[PrimeTower] = None
        self._golden: Optional[np.ndarray] = None
        self._primes: Optional[np.ndarray] = None

    # ── ladders ─────────────────────────────────────────────────────
    @property
    def tower(self) -> PrimeTower:
        if self._tower is None:
            self._tower = PrimeTower(max_level=self.cfg.tower_max_level)
        return self._tower

    def golden_ladder(self) -> np.ndarray:
        """ω_k = omega_base · PHI^k for k = 0..n_golden-1.

        The same ladder KuramotoField uses with `ladder="golden_powers"`.
        """
        if self._golden is None:
            k = np.arange(self.cfg.n_golden, dtype=np.float64)
            self._golden = self.cfg.omega_base * (PHI ** k)
        return self._golden.copy()

    def prime_ladder(self) -> np.ndarray:
        """[p_2, p_3, ..., p_tower_max_level].

        The prime tower levels start at 2. Level n contributes p_n.
        """
        if self._primes is None:
            self._primes = np.array(
                [
                    float(self.tower.prime(n))
                    for n in range(2, self.cfg.tower_max_level + 1)
                ],
                dtype=np.float64,
            )
        return self._primes.copy()

    def epsilon(self) -> float:
        """The residual grid quantum. Used by downstream consumers, not
        by the cascade itself."""
        return float(self.cfg.epsilon)

    # ── cascade ─────────────────────────────────────────────────────
    def cascade(self) -> SkeletonSpectrum:
        """Walk the skeleton and emit the D_res spectrum.

        The composition rule is set by cfg.composition. The result is
        deterministic given the config.
        """
        comp = self.cfg.composition
        if comp == "golden_x_prime":
            n = min(self.cfg.n_golden, len(self.prime_ladder()))
            g = self.golden_ladder()[:n]
            p = self.prime_ladder()[:n]
            spec = SkeletonSpectrum(
                eigenvalues=g * p,
                multiplicities=np.ones(n, dtype=np.int64),
            )
        elif comp == "golden_with_prime_mult":
            g = self.golden_ladder()
            n = len(g)
            p = self.prime_ladder()[:n]
            spec = SkeletonSpectrum(
                eigenvalues=g,
                multiplicities=p.astype(np.int64),
            )
        else:
            raise ValueError(f"unknown composition: {comp!r}")
        d = spec.to_dict()
        d["composition"] = comp
        return spec

    # ── introspection ───────────────────────────────────────────────
    def describe(self) -> dict:
        return {
            "epsilon": self.cfg.epsilon,
            "n_golden": self.cfg.n_golden,
            "omega_base": self.cfg.omega_base,
            "tower_max_level": self.cfg.tower_max_level,
            "composition": self.cfg.composition,
            "n_primes": len(self.prime_ladder()),
            "golden_ladder_head": self.golden_ladder()[:4].tolist(),
            "prime_ladder_head": self.prime_ladder()[:4].tolist(),
        }

    def __repr__(self) -> str:
        return (
            f"SpectralSkeleton(n_golden={self.cfg.n_golden}, "
            f"tower_max_level={self.cfg.tower_max_level}, "
            f"composition={self.cfg.composition!r})"
        )


__all__ = [
    "SpectralSkeleton",
    "SpectralSkeletonConfig",
    "SkeletonSpectrum",
]
