"""Bridge from the scale address to the residual core and evolution search.

Uses ResidualCore.step and OscillatorOrientedSearch when the package
is importable. Fallback path keeps the same return shape.
"""
from __future__ import annotations

from typing import Any

import numpy as np

try:
    from resileos.core import CoreConfig, ResidualCore
    _HAS_CORE = True
except ImportError:
    ResidualCore = None
    CoreConfig = None
    _HAS_CORE = False

def _search_types():
    try:
        from resileos.evolution_oscillator import OscillatorOrientedSearch
        from resileos.substrate.oscillator import KuramotoField
    except ImportError:
        return None, None
    return OscillatorOrientedSearch, KuramotoField


def core_step_from_address(embed: dict[str, Any], size: int = 4) -> dict[str, Any]:
    """Run one residual core step seeded from the address, or a fallback."""
    if _HAS_CORE and ResidualCore is not None and CoreConfig is not None:
        cfg = CoreConfig(m=size, n=size, r=2, n_residual_layers=2)
        core = ResidualCore(cfg, seed=abs(hash(embed.get("residual_bin", ""))) % (2**31))
        W = np.eye(size) * (0.5 + embed.get("mean_luma", 0.5))
        packet = core.step(W)
        return {
            "backend": "residual_core",
            "packet_hash": getattr(packet, "hash", None) or str(hash(str(packet)))[:12],
            "layers": cfg.n_residual_layers,
        }
    # fallback: deterministic token from the address
    token = f"{embed.get('belt')}:{embed.get('frame')}:{embed.get('residual_bin')}"
    return {
        "backend": "fallback",
        "packet_hash": str(abs(hash(token)) % (10**8)),
        "layers": 0,
    }


def search_from_field(theta: list[float]) -> dict[str, Any]:
    """Build an oscillator-oriented search biased by the field phases."""
    OscillatorOrientedSearch, KuramotoField = _search_types()
    if OscillatorOrientedSearch is not None and KuramotoField is not None:
        field = KuramotoField(3)
        field.theta = np.array(theta[:3] if len(theta) >= 3 else [0.0, 0.0, 0.0])
        search = OscillatorOrientedSearch(field=field, budget=8, seed=0)
        return {
            "backend": "oscillator_search",
            "budget": search.budget,
            "n_candidates": len(getattr(search, "r_values", [])) * len(getattr(search, "n_loops_values", [])),
        }
    return {
        "backend": "fallback",
        "budget": 0,
        "n_candidates": 0,
    }
