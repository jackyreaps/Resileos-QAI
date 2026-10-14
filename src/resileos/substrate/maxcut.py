"""MaxCut instance generator and mode-labelling helper for RES-304.

The triad experiment uses MaxCut as its test problem: a random graph on n
vertices, cut value = number of edges crossing the partition. Basins are
partitions; the target mode is the best-known partition found by any
comparison method (random search, local search, simulated annealing).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MaxCutInstance:
    n: int
    adjacency: np.ndarray   # (n, n) symmetric 0/1

    def cut_value(self, partition: np.ndarray) -> int:
        """Number of edges crossing the bipartition given by ±1 labels."""
        p = np.asarray(partition, dtype=float)
        s = p[:, None] * p[None, :]           # +1 same side, -1 crossing
        cross = (s < 0).astype(int)
        # symmetric matrix: halve to count each edge once
        return int(np.sum(cross * self.adjacency) // 2)


def random_maxcut(n: int, edge_prob: float = 0.5, seed: int = 0) -> MaxCutInstance:
    rng = np.random.default_rng(seed)
    upper = (rng.random((n, n)) < edge_prob).astype(int)
    upper = np.triu(upper, k=1)
    A = upper + upper.T
    return MaxCutInstance(n=n, adjacency=A)


def random_partition(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.choice([-1.0, 1.0], size=n)


def local_search(
    inst: MaxCutInstance,
    init: np.ndarray,
    max_iter: int = 200,
) -> np.ndarray:
    """Flip single vertices greedily until no improving flip exists."""
    p = init.copy()
    cur = inst.cut_value(p)
    for _ in range(max_iter):
        improved = False
        for i in range(inst.n):
            p[i] *= -1
            new = inst.cut_value(p)
            if new > cur:
                cur = new
                improved = True
            else:
                p[i] *= -1
        if not improved:
            break
    return p


def simulated_annealing(
    inst: MaxCutInstance,
    init: np.ndarray,
    steps: int = 2000,
    t0: float = 2.0,
    t1: float = 0.01,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p = init.copy()
    cur = inst.cut_value(p)
    T = t0
    decay = (t1 / t0) ** (1.0 / steps)
    for _ in range(steps):
        i = int(rng.integers(inst.n))
        p[i] *= -1
        new = inst.cut_value(p)
        if new >= cur or rng.random() < np.exp((new - cur) / max(T, 1e-9)):
            cur = new
        else:
            p[i] *= -1
        T *= decay
    return p
