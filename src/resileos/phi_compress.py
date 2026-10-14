"""
φ-compression.

One contraction step multiplies an integer quantity by
phi_hat = 1/phi = phi - 1, floored and clamped to a minimum. Uses PHI
from the oscillator module and golden_ladder for the ladder prefix.

Worked examples: rank 8 -> 4, depth 64 -> 39.
"""
from __future__ import annotations

import numpy as np

from .core import CoreConfig
from .substrate.oscillator import PHI, golden_ladder


PHI_HAT = 1.0 / PHI


def contract_rank(r: int, min_rank: int = 1) -> int:
    if r < 0:
        raise ValueError("r must be >= 0")
    if min_rank < 1:
        raise ValueError("min_rank must be >= 1")
    return max(min_rank, int(np.floor(r * PHI_HAT)))


def contract_depth(L: int, min_depth: int = 1) -> int:
    return contract_rank(L, min_rank=min_depth)


def contract_repeated(value: int, steps: int = 1,
                      min_value: int = 1) -> int:
    if steps < 0:
        raise ValueError("steps must be >= 0")
    v = int(value)
    for _ in range(steps):
        v_new = max(min_value, int(np.floor(v * PHI_HAT)))
        if v_new == v:
            break
        v = v_new
    return v


def zeckendorf_rank(n: int) -> int:
    """Number of non-consecutive Fibonacci terms (1, 2, 3, 5, ...)
    needed to represent n. zeckendorf_rank(0) = 0."""
    if n <= 0:
        return 0
    fibs = [1, 2]
    while fibs[-1] < n:
        fibs.append(fibs[-1] + fibs[-2])
    count = 0
    remaining = int(n)
    for f in reversed(fibs):
        if f <= remaining:
            remaining -= f
            count += 1
        if remaining == 0:
            break
    return count


def select_by_zeckendorf(n: int, keep: int) -> np.ndarray:
    if n <= 0:
        raise ValueError("n must be >= 1")
    if keep < 0 or keep > n:
        raise ValueError("keep must be in [0, n]")
    ranks = np.array([zeckendorf_rank(i + 1) for i in range(n)],
                     dtype=np.int64)
    order = np.lexsort((np.arange(n), ranks))
    return np.sort(order[:keep]).astype(np.int64)


def contracted_ladder(r: int, min_rank: int = 1) -> np.ndarray:
    """golden_ladder at the contracted rank."""
    return golden_ladder(contract_rank(r, min_rank=min_rank))


def contract_config(cfg: CoreConfig, min_rank: int = 1) -> CoreConfig:
    """Return a new CoreConfig with r contracted one step. Input
    unchanged."""
    return CoreConfig(
        m=cfg.m, n=cfg.n, r=contract_rank(cfg.r, min_rank=min_rank),
        alpha=cfg.alpha, beta=cfg.beta, gamma=cfg.gamma,
        n_residual_layers=cfg.n_residual_layers,
    )


__all__ = [
    "PHI_HAT",
    "contract_rank", "contract_depth", "contract_repeated",
    "zeckendorf_rank", "select_by_zeckendorf",
    "contracted_ladder", "contract_config",
]
