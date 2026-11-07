"""Residual function for the scale address.

Placeholder that is stable and deterministic.
Replace the body with the suite residual when it is coded.
The callers do not change.
"""
from __future__ import annotations


def suite_residual(mean_luma: float, edge_density: float, belt: int = 0) -> str:
    """Deterministic residual label.

    This is the swap point. When the suite residual is available,
    replace this body. Callers keep the same signature.
    """
    # coarse but stable: 4 bins from two thresholds, belt mod for scale
    luma_hi = mean_luma > 0.5
    edge_hi = edge_density > 0.15
    scale = belt % 4
    return f"r{int(luma_hi)}{int(edge_hi)}_s{scale}"
