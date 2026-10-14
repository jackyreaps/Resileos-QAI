"""Sheath detection for the size regime of the RES-304 landscape.

Definition (operational, from the size argument):

    At small n the basin boundary behaves as a constraint. It has finite
    depth: a perturbation of magnitude < depth crosses the boundary and
    returns. boundary_codim is O(1); d_b is well below n-1.

    At large n with layered masks the boundary saturates. boundary_codim -> 0
    (the boundary fills the space) and depth -> 0 (crossings stop being
    reversible). That regime is the sheath.

Neither condition alone is sufficient. A high-dimension boundary with finite
depth is still a constraint. A shallow boundary with low dimension is a wall
in one direction, not a sheath. Both must hold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .basin import BasinConfig, measure_basin


@dataclass
class SheathConfig:
    codim_max: float = 0.5        # codimension below this = boundary fills space
    depth_min: float = 0.05       # depth below this = crossings not reversible
    basin: Optional[BasinConfig] = None


def sheath_metrics(
    step_fn: Callable[[np.ndarray], int],
    target_mode: int,
    cfg: BasinConfig,
    sheath_cfg: Optional[SheathConfig] = None,
    anchor: Optional[np.ndarray] = None,
    directions=None,
) -> dict:
    """Measure the landscape and classify constraint vs sheath."""
    if sheath_cfg is None:
        sheath_cfg = SheathConfig()

    res = measure_basin(
        step_fn, target_mode, cfg, anchor=anchor, directions=directions
    )

    n = cfg.n_dims
    # normalized boundary dimension: 0 = point, 1 = fills the (n-1) sphere
    norm_dim = res.boundary_dim / max(n - 1, 1)
    codim = res.boundary_codim

    saturated = codim < sheath_cfg.codim_max
    collapsed = res.depth < sheath_cfg.depth_min
    is_sheath = bool(saturated and collapsed)

    if not saturated and not collapsed:
        regime = "constraint"
    elif saturated and not collapsed:
        regime = "saturated-boundary"   # high-dim but still crossable
    elif collapsed and not saturated:
        regime = "wall"                  # shallow but localized
    else:
        regime = "sheath"

    return {
        "n": int(n),
        "volume": res.volume,
        "depth": res.depth,
        "boundary_dim": res.boundary_dim,
        "boundary_codim": codim,
        "norm_boundary_dim": float(norm_dim),
        "hopping_rate": res.hopping_rate,
        "basin_entropy": res.basin_entropy,
        "saturated": saturated,
        "collapsed": collapsed,
        "is_sheath": is_sheath,
        "regime": regime,
    }
