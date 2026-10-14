"""Basin metrics for the RES-304 triad.

Four metrics per the spec:
    volume         fraction of random initial states that converge to target
    depth          largest perturbation magnitude that leaves the mode intact
    boundary_dim   fractal dimension of the basin boundary
    hopping_rate   mode crossings per unit time under small noise

Plus two additions for the size regime:
    boundary_codim   n - d_b, estimated in the full state space (not a 2D slice)
    basin_entropy    effective number of occupied basins

At low n the boundary is a constraint: finite depth, d_b well below n-1.
At high n with layered masks the boundary saturates: d_b -> n-1, depth -> 0.
That regime is the sheath. See docs/300-substrate/sheath.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np


@dataclass
class BasinConfig:
    n_states: int = 200
    n_dims: int = 10
    depth_bisect_steps: int = 12
    depth_max_perturbation: float = 2.0
    boundary_grid: int = 32
    hop_duration: int = 200
    hop_noise: float = 1e-3
    codim_pairs: int = 200
    codim_deltas: tuple = (0.5, 0.25, 0.125, 0.0625)
    seed: int = 0


@dataclass
class BasinResult:
    volume: float
    depth: float
    boundary_dim: float
    hopping_rate: float
    n_used: int
    mode_counts: dict[int, int]
    boundary_codim: float = 0.0
    basin_entropy: float = 0.0

    def to_dict(self) -> dict:
        return {
            "volume": float(self.volume),
            "depth": float(self.depth),
            "boundary_dim": float(self.boundary_dim),
            "hopping_rate": float(self.hopping_rate),
            "n_used": int(self.n_used),
            "mode_counts": {int(k): int(v) for k, v in self.mode_counts.items()},
            "boundary_codim": float(self.boundary_codim),
            "basin_entropy": float(self.basin_entropy),
        }


def basin_volume(step_fn, target_mode, cfg):
    rng = np.random.default_rng(cfg.seed)
    counts: dict[int, int] = {}
    hits = 0
    for _ in range(cfg.n_states):
        x0 = rng.uniform(-1.0, 1.0, size=cfg.n_dims)
        mode = int(step_fn(x0))
        counts[mode] = counts.get(mode, 0) + 1
        if mode == target_mode:
            hits += 1
    return hits / cfg.n_states, counts


def basin_entropy(mode_counts: dict[int, int]) -> float:
    """Effective number of occupied basins. 1.0 = all inits in one basin."""
    total = sum(mode_counts.values())
    if total == 0:
        return 0.0
    p = np.array([c / total for c in mode_counts.values()], dtype=float)
    p = p[p > 0]
    h = -np.sum(p * np.log(p))
    return float(np.exp(h))


def basin_depth(step_fn, anchor, target_mode, cfg, directions=None):
    """Largest L2 perturbation that keeps convergence to target_mode.

    If directions is None, uses 4 random unit directions (existing behavior).
    Pass an explicit (k, n_dims) array to probe structured axes — e.g. the
    mask-bit axes — so depth is measured across the boundary you care about.
    """
    rng = np.random.default_rng(cfg.seed + 1)
    if directions is None:
        dirs = []
        for _ in range(4):
            u = rng.standard_normal(cfg.n_dims)
            dirs.append(u / (np.linalg.norm(u) + 1e-12))
    else:
        dirs = [np.asarray(d, dtype=float) for d in directions]

    worst = float("inf")
    for u in dirs:
        lo, hi = 0.0, cfg.depth_max_perturbation
        for _ in range(8):
            probe = anchor + hi * u
            if int(step_fn(probe)) != target_mode:
                break
            hi *= 1.5
        for _ in range(cfg.depth_bisect_steps):
            mid = 0.5 * (lo + hi)
            probe = anchor + mid * u
            if int(step_fn(probe)) == target_mode:
                lo = mid
            else:
                hi = mid
        worst = min(worst, lo)
    return float(worst)


def basin_boundary_dim(step_fn, target_mode, cfg):
    """Box-counting dimension of the basin boundary in a 2D slice.

    Valid diagnostic for the constraint regime at small n. Saturated at 1.0
    for any boundary that fills more than a curve, so it cannot distinguish
    a fractal sheet from a curve. Use boundary_codimension for the full space.
    """
    g = cfg.boundary_grid
    x = np.linspace(-1.0, 1.0, g)
    y = np.linspace(-1.0, 1.0, g)
    labels = np.zeros((g, g), dtype=int)
    base = np.zeros(cfg.n_dims)
    for i, xv in enumerate(x):
        for j, yv in enumerate(y):
            p = base.copy()
            p[0], p[1] = xv, yv
            labels[i, j] = int(step_fn(p))

    boundary = np.zeros_like(labels, dtype=bool)
    boundary[:-1, :] |= labels[:-1, :] != labels[1:, :]
    boundary[1:, :] |= labels[:-1, :] != labels[1:, :]
    boundary[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    boundary[:, 1:] |= labels[:, :-1] != labels[:, 1:]

    sizes = [s for s in (2, 4, 8, 16) if s <= g]
    counts = []
    used = []
    for s in sizes:
        blocks = g // s
        c = 0
        for bi in range(blocks):
            for bj in range(blocks):
                if boundary[bi * s:(bi + 1) * s, bj * s:(bj + 1) * s].any():
                    c += 1
        counts.append(c)
        used.append(s)
    if len(counts) < 2 or any(c == 0 for c in counts):
        return 0.0
    slope, _ = np.polyfit(
        np.log(1.0 / np.array(used, dtype=float)),
        np.log(np.array(counts, dtype=float)),
        1,
    )
    return float(slope)


def boundary_codimension(step_fn, cfg) -> float:
    """Estimate n - d_b in the full state space.

    Sample random pairs at separation delta, measure P(straddle) = fraction
    where the two endpoints land in different basins. For a boundary of
    dimension d_b, P(straddle) ~ delta^(n - d_b). Fit log P vs log delta.

    Returns the codimension n - d_b. Codim -> 0 means the boundary fills the
    space (sheath). Codim ~ 1 means it is a thin surface (constraint).
    """
    rng = np.random.default_rng(cfg.seed + 3)
    deltas = np.asarray(cfg.codim_deltas, dtype=float)
    ps = []
    for d in deltas:
        straddles = 0
        for _ in range(cfg.codim_pairs):
            a = rng.uniform(-1.0, 1.0, size=cfg.n_dims)
            u = rng.standard_normal(cfg.n_dims)
            u /= np.linalg.norm(u) + 1e-12
            b = a + d * u
            if int(step_fn(a)) != int(step_fn(b)):
                straddles += 1
        ps.append(straddles / cfg.codim_pairs)
    ps = np.array(ps, dtype=float)
    # guard against zeros: floor at 1/(2 * pairs)
    floor = 1.0 / (2.0 * cfg.codim_pairs)
    ps = np.maximum(ps, floor)
    slope, _ = np.polyfit(np.log(deltas), np.log(ps), 1)
    return float(slope)


def basin_hopping_rate(step_fn, anchor, target_mode, cfg):
    rng = np.random.default_rng(cfg.seed + 2)
    x = anchor.copy()
    prev = int(step_fn(x)) == target_mode
    crossings = 0
    for _ in range(cfg.hop_duration):
        x = x + cfg.hop_noise * rng.standard_normal(cfg.n_dims)
        cur = int(step_fn(x)) == target_mode
        if cur != prev:
            crossings += 1
        prev = cur
    return crossings / cfg.hop_duration


def measure_basin(step_fn, target_mode, cfg, anchor=None, directions=None):
    if anchor is None:
        anchor = np.zeros(cfg.n_dims)
    volume, counts = basin_volume(step_fn, target_mode, cfg)
    depth = basin_depth(step_fn, anchor, target_mode, cfg, directions=directions)
    bdim = basin_boundary_dim(step_fn, target_mode, cfg)
    hop = basin_hopping_rate(step_fn, anchor, target_mode, cfg)
    codim = boundary_codimension(step_fn, cfg)
    entropy = basin_entropy(counts)
    return BasinResult(
        volume=volume,
        depth=depth,
        boundary_dim=bdim,
        hopping_rate=hop,
        n_used=cfg.n_states,
        mode_counts=counts,
        boundary_codim=codim,
        basin_entropy=entropy,
    )
