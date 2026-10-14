"""Primorial carriers for sub-category resolution (RES-312 extension).

A primorial is the product of the first k primes:

    P_k = p_1 * p_2 * ... * p_k
    P_1 = 2, P_2 = 6, P_3 = 30, P_4 = 210, P_5 = 2310, P_6 = 30030

Primorials grow much faster than primes. The Nyquist bound p < dim/2
becomes P_k < dim/2, so the usable count collapses quickly:

    dim = 64    P_k < 32 -> k <= 3   (2, 6, 30)
    dim = 512   P_k < 256 -> k <= 4  (2, 6, 30, 210)
    dim = 4096  P_k < 2048 -> k <= 5 (2, 6, 30, 210, 2310)

Primorial carriers nest: P_k contains all smaller prime factors, so a
carrier at level k resolves sub-categories at every divisor of P_k.
This is the structural complement to the prime tower's single-prime
levels — the tower gives depth, the primorial gives sub-category
containment within a depth level.

Off states:
    semantic claim     off. Levels are construction indices.
    capacity claim     off. Bounded by Nyquist, same as the tower.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .prime_tower import PrimeTower


def _first_n_primes(n: int) -> list[int]:
    """Local copy to avoid a hard dependency on PrimeTower internals."""
    if n < 1:
        return []
    limit = 15 if n < 6 else int(n * (math.log(n) + math.log(math.log(n)))) + 10
    sieve = bytearray([1]) * (limit + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i :: i] = bytearray(len(range(i * i, limit + 1, i)))
    primes = [i for i in range(2, limit + 1) if sieve[i]]
    while len(primes) < n:
        limit *= 2
        sieve = bytearray([1]) * (limit + 1)
        sieve[0] = sieve[1] = 0
        for i in range(2, int(limit ** 0.5) + 1):
            if sieve[i]:
                sieve[i * i :: i] = bytearray(len(range(i * i, limit + 1, i)))
        primes = [i for i in range(2, limit + 1) if sieve[i]]
    return primes[:n]


def primorial(k: int, primes: Optional[list[int]] = None) -> int:
    """P_k = product of first k primes. P_0 = 1 by convention."""
    if k < 0:
        raise ValueError("k must be >= 0")
    if k == 0:
        return 1
    ps = primes if primes is not None else _first_n_primes(k)
    if len(ps) < k:
        raise ValueError(f"need {k} primes, got {len(ps)}")
    out = 1
    for p in ps[:k]:
        out *= int(p)
    return out


def n_usable_primorials(dim: int, max_k: int = 12) -> int:
    """Largest k such that P_k < dim/2."""
    if dim < 4:
        raise ValueError("dim must be >= 4")
    nyquist = dim // 2
    primes = _first_n_primes(max_k)
    p = 1
    k = 0
    for i in range(max_k):
        if p * primes[i] < nyquist:
            p *= primes[i]
            k += 1
        else:
            break
    return k


def primorial_carrier(k: int, dim: int) -> np.ndarray:
    """Carrier for primorial level k.

        P = primorial(k)
        phase[d] = 2π · P · d / dim
        carrier[d] = exp(i · phase[d]) / sqrt(dim)

    Nyquist bound: P_k < dim/2.
    """
    if dim < 4:
        raise ValueError("dim must be >= 4")
    if k < 1:
        raise ValueError("k must be >= 1")
    P = primorial(k)
    if 2 * P >= dim:
        raise ValueError(
            f"primorial P_{k}={P} exceeds Nyquist at dim={dim} "
            f"(requires 2P < dim)"
        )
    d = np.arange(dim, dtype=np.float64)
    phases = 2.0 * np.pi * float(P) * d / float(dim)
    return np.exp(1j * phases) / np.sqrt(dim)


__all__ = [
    "primorial",
    "n_usable_primorials",
    "primorial_carrier",
]
