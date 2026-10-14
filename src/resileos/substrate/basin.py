"""Basin metrics for the RES-304 triad.

Four metrics per the spec:

  volume            fraction of random initial states that converge to the
                    target mode under the constraint graph's dynamics
  depth             largest perturbation magnitude that leaves the mode intact
                    (measured by bisection on perturbation amplitude)
  boundary_dim      box-counting fractal dimension of the basin boundary
  hopping_rate      expected number of mode crossings per unit time under
                    a small noise drive

These are read-only measurements over a callable `step` that maps
(state, perturbation) -> terminal mode index. The caller supplies the
dynamics; this module only measures their landscape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class BasinConfig:
    n_states: int = 200         # K random initializations
    n_dims: int = 10            # problem size (MaxCut n)
    depth_bisect_steps: int = 12
    depth_max_perturbation: float = 2.0
    boundary_grid: int = 32     # box-counting resolution
    hop_duration: int = 200
    hop_noise: float = 1e-3
    seed: int = 0


# ── result ──────────────────────────────────────────────────────────────
@dataclass
class BasinResult:
    volume: float
    depth: float
    boundary_dim: float
    hopping_rate: float
    n_used: int
    mode_counts: dict[int, int]   # which mode each init landed in

    def to_dict(self) -> dict:
        return {
            "volume": float(self.volume),
            "depth": float(self.depth),
            "boundary_dim": float(self.boundary_dim),
            "hopping_rate": float(self.hopping_rate),
            "n_used": int(self.n_used),
            "mode_counts": {int(k): int(v) for k, v in self.mode_counts.items()},
        }


# ── volume ──────────────────────────────────────────────────────────────
def basin_volume(
    step_fn: Callable[[np.ndarray], int],
    target_mode: int,
    cfg: BasinConfig,
) -> tuple[float, dict[int, int]]:
    """Fraction of random initial states converging to target_mode."""
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


# ── depth ───────────────────────────────────────────────────────────────
def basin_depth(
    step_fn: Callable[[np.ndarray], int],
    anchor: np.ndarray,
    target_mode: int,
    cfg: BasinConfig,
) -> float:
    """Largest L2 perturbation amplitude that keeps convergence to target_mode.

    Bisection on amplitude along a random unit direction. Repeated over a small
    set of directions; the reported depth is the min over directions (worst case
    perturbation the basin tolerates).
    """
    rng = np.random.default_rng(cfg.seed + 1)
    n_dirs = 4
    worst = float("inf")
    for _ in range(n_dirs):
        u = rng.standard_normal(cfg.n_dims)
        u /= np.linalg.norm(u) + 1e-12
        lo, hi = 0.0, cfg.depth_max_perturbation
        # establish an upper bound where the mode breaks
        for _ in range(8):
            probe = anchor + hi * u
            if int(step_fn(probe)) != target_mode:
                break
            hi *= 1.5
        # bisection between lo (safe) and hi (broken)
        for _ in range(cfg.depth_bisect_steps):
            mid = 0.5 * (lo + hi)
            probe = anchor + mid * u
            if int(step_fn(probe)) == target_mode:
                lo = mid
            else:
                hi = mid
        worst = min(worst, lo)
    return float(worst)


# ── boundary dimension ──────────────────────────────────────────────────
def basin_boundary_dim(
    step_fn: Callable[[np.ndarray], int],
    target_mode: int,
    cfg: BasinConfig,
) -> float:
    """Box-counting dimension of the basin boundary in a 2D slice.

    Fix all but two coordinates at their mid-values, sweep a 2D grid, and
    count cells where the mode label differs from at least one neighbor.
    Fit log(count) vs log(1/box_size) to get the slope.
    """
    g = cfg.boundary_grid
    x = np.linspace(-1.0, 1.0, g)
    y = np.linspace(-1.0, 1.0, g)
    labels = np.zeros((g, g), dtype=int)
    base = np.zeros(cfg.n_dims)

    # full-resolution label grid
    for i, xv in enumerate(x):
        for j, yv in enumerate(y):
            p = base.copy()
            p[0], p[1] = xv, yv
            labels[i, j] = int(step_fn(p))

    # boundary cells: any neighbor with different label
    boundary = np.zeros_like(labels, dtype=bool)
    boundary[:-1, :] |= labels[:-1, :] != labels[1:, :]
    boundary[1:, :] |= labels[:-1, :] != labels[1:, :]
    boundary[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    boundary[:, 1:] |= labels[:, :-1] != labels[:, 1:]

    # box-counting at multiple scales
    sizes = [2, 4, 8, 16]
    counts = []
    used = []
    for s in sizes:
        if s > g:
            continue
        blocks = g // s
        c = 0
        for bi in range(blocks):
            for bj in range(blocks):
                if boundary[
                    bi * s : (bi + 1) * s, bj * s : (bj + 1) * s
                ].any():
                    c += 1
        counts.append(c)
        used.append(s)

    if len(counts) < 2 or any(c == 0 for c in counts):
        return 0.0
    log_inv_s = np.log(1.0 / np.array(used, dtype=float))
    log_c = np.log(np.array(counts, dtype=float))
    slope, _ = np.polyfit(log_inv_s, log_c, 1)
    return float(slope)


# ── hopping rate ────────────────────────────────────────────────────────
def basin_hopping_rate(
    step_fn: Callable[[np.ndarray], int],
    anchor: np.ndarray,
    target_mode: int,
    cfg: BasinConfig,
) -> float:
    """Expected mode crossings per unit time under a small noise drive.

    Iterate a perturbed state for hop_duration steps, count sign changes of
    (mode(t) != target_mode) transitions. Rate = crossings / duration.
    """
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


# ── combined ────────────────────────────────────────────────────────────
def measure_basin(
    step_fn: Callable[[np.ndarray], int],
    target_mode: int,
    cfg: BasinConfig,
    anchor: Optional[np.ndarray] = None,
) -> BasinResult:
    if anchor is None:
        anchor = np.zeros(cfg.n_dims)

    volume, counts = basin_volume(step_fn, target_mode, cfg)
    depth = basin_depth(step_fn, anchor, target_mode, cfg)
    boundary_dim = basin_boundary_dim(step_fn, target_mode, cfg)
    hopping = basin_hopping_rate(step_fn, anchor, target_mode, cfg)

    return BasinResult(
        volume=volume,
        depth=depth,
        boundary_dim=boundary_dim,
        hopping_rate=hopping,
        n_used=cfg.n_states,
        mode_counts=counts,
    )
