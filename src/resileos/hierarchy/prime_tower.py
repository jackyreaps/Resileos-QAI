"""Prime tower (X-Files 06-prime-tower-hypothesis.md).

The tower is a nested-division sequence built from primes normalised by
the three-term Cipolla approximant:

    S_k = p_k / D_k                (k >= 3)
    S_1 = p_1 / 2 = 1
    S_2 = p_2 / 3 = 1
    T(2) = S_2
    T(n) = S_n / T(n-1)            (n >= 3)

where p_k is the k-th prime and

    D_k = k (ln k + ln ln k - 1 + (ln ln k - 2) / ln k)

The tower stabilises to a reciprocal pair:
    L_even ~ 1.060
    L_odd  ~ 0.943

The odd branch is domain-forbidden for x^{x-1} = T(n) because
x^{x-1} >= 1 for all real x > 0. The even branch has exactly two real
positive roots.

This module implements the tower's construction: primes, Cipolla
approximants, normalised terms, tower terms, and branch assignment.
It does not implement any downstream consumer.

Off states (explicit):
    stochastic extension   off. The tower is deterministic given
                           max_level.
    semantic claim         off. Tower levels are construction indices,
                           not semantically ordered.
    capacity claim         off. The tower's usable layer count is
                           bounded by the Nyquist limit p_n < dim/2.
    domain-wall proof      off. The odd branch is domain-forbidden for
                           the coupled transcendental system. The tower
                           term T(n) itself is well-defined for both
                           branches.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

import numpy as np


# ── prime sieve ─────────────────────────────────────────────────────
def _sieve_primes(limit: int) -> list[int]:
    """Return all primes <= limit."""
    if limit < 2:
        return []
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            step = i
            start = i * i
            sieve[start : limit + 1 : step] = bytearray(
                len(range(start, limit + 1, step))
            )
    return [i for i in range(2, limit + 1) if sieve[i]]


def _first_n_primes(n: int) -> list[int]:
    """Return the first n primes."""
    if n < 1:
        return []
    if n < 6:
        limit = 15
    else:
        limit = int(n * (math.log(n) + math.log(math.log(n)))) + 10
    primes = _sieve_primes(limit)
    while len(primes) < n:
        limit *= 2
        primes = _sieve_primes(limit)
    return primes[:n]


# ── Cipolla approximant ─────────────────────────────────────────────
def cipolla(k: int) -> float:
    """Three-term Cipolla approximant D_k for the k-th prime.

    The raw formula is negative for small k (k=3 gives ~-4.63). The
    X-Files script's convention clamps to a small positive floor. This
    function does the same: it returns the raw value when positive,
    and a small floor otherwise. The tower term T(n) is well-defined
    under this convention; the asymptotic behaviour is unchanged.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if k < 3:
        # Convention: S_1 = p_1 / 2, S_2 = p_2 / 3.
        # D_1 and D_2 are not used; return a placeholder.
        return float(k)
    lnk = math.log(k)
    lnlnk = math.log(lnk)
    raw = k * (lnk + lnlnk - 1.0 + (lnlnk - 2.0) / lnk)
    return max(raw, 1e-12)


# ── tower ───────────────────────────────────────────────────────────
class PrimeTower:
    """Prime tower with Cipolla normalisation.

    Construction:
        tower = PrimeTower(max_level=64)
        p = tower.prime(3)          # 5
        T = tower.T(3)              # tower term at level 3
        branch = tower.branch(3)    # 'odd'
        usable = tower.n_usable(512) # 54

    Levels are indexed from 2 (T(2) = S_2). Level 1 is not part of the
    recurrence; p_1 is used only to define S_1.
    """

    def __init__(self, max_level: int = 128) -> None:
        # Coerce first, then compare. Comparing before coercion raises
        # TypeError on string input instead of the intended ValueError.
        max_level = int(max_level)
        if max_level < 2:
            raise ValueError("max_level must be >= 2")
        self.max_level = max_level
        # We need primes p_1 .. p_max_level
        self._primes: list[int] = _first_n_primes(max_level)
        # Precompute S_k and T(n) lazily via lru_cache on methods
        self._cipolla_cache: dict[int, float] = {}

    # ── primes ──────────────────────────────────────────────────────
    def prime(self, k: int) -> int:
        """Return the k-th prime (1-indexed)."""
        if not (1 <= k <= self.max_level):
            raise ValueError(
                f"k {k} out of range [1, {self.max_level}]"
            )
        return self._primes[k - 1]

    @property
    def primes(self) -> list[int]:
        return list(self._primes)

    # ── normalised terms ────────────────────────────────────────────
    def S(self, k: int) -> float:
        """Normalised term S_k = p_k / D_k.

        Conventions (from the X-Files correction, Oct 2026):
            S_1 = p_1 / 2 = 1
            S_2 = p_2 / 3 = 1
            S_k = p_k / D_k   for k >= 3
        """
        if not (1 <= k <= self.max_level):
            raise ValueError(
                f"k {k} out of range [1, {self.max_level}]"
            )
        if k == 1:
            return float(self._primes[0]) / 2.0
        if k == 2:
            return float(self._primes[1]) / 3.0
        if k not in self._cipolla_cache:
            self._cipolla_cache[k] = cipolla(k)
        d = self._cipolla_cache[k]
        return float(self._primes[k - 1]) / d

    # ── tower terms ─────────────────────────────────────────────────
    def T(self, n: int) -> float:
        """Tower term T(n).

            T(2) = S_2
            T(n) = S_n / T(n-1)   for n >= 3
        """
        if not (2 <= n <= self.max_level):
            raise ValueError(
                f"n {n} out of range [2, {self.max_level}]"
            )
        if n == 2:
            return self.S(2)
        return self.S(n) / self.T(n - 1)

    # ── branch ──────────────────────────────────────────────────────
    @staticmethod
    def branch(n: int) -> str:
        """Branch assignment. Even n -> 'even', odd n -> 'odd'."""
        if n < 2:
            raise ValueError("n must be >= 2")
        return "even" if n % 2 == 0 else "odd"

    def is_forbidden(self, n: int) -> bool:
        """True when the tower level is on the domain-forbidden side.

        The odd branch is domain-forbidden for the coupled system
        x^{x-1} = T(n) because x^{x-1} >= 1 for all real x > 0.
        This is a structural property, not a numerical threshold.
        """
        if not (2 <= n <= self.max_level):
            raise ValueError(
                f"n {n} out of range [2, {self.max_level}]"
            )
        return self.branch(n) == "odd"

    # ── Nyquist bound ───────────────────────────────────────────────
    def n_usable(self, dim: int) -> int:
        """Number of tower levels whose prime frequency fits under
        the Nyquist bound p_n < dim / 2.

        At dim=64, the largest usable prime is 31 (p_11), so
        n_usable=10 (levels 2..11). At dim=512, the largest usable
        prime is 251 (p_54), so n_usable=53 (levels 2..54).
        """
        if dim < 4:
            raise ValueError("dim must be >= 4")
        nyquist = dim // 2
        count = 0
        for n in range(2, self.max_level + 1):
            if self._primes[n - 1] < nyquist:
                count += 1
            else:
                break
        return count

    def max_usable_level(self, dim: int) -> int:
        """Highest tower level whose prime fits under Nyquist."""
        n = self.n_usable(dim)
        return 1 + n if n > 0 else 0

    # ── introspection ───────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {
            "max_level": int(self.max_level),
            "primes": list(self._primes),
            "S": {k: self.S(k) for k in range(1, min(8, self.max_level + 1))},
            "T": {n: self.T(n) for n in range(2, min(8, self.max_level + 1))},
        }

    def __repr__(self) -> str:
        return f"PrimeTower(max_level={self.max_level})"


__all__ = ["PrimeTower", "cipolla"]
