"""Prior-framework numbers for the substrate oscillator.

One editable place for the address base, the recovery scale, and the
phase per debt quantum. ``KuramotoField`` reads the outward weight from
``outward_weight`` instead of a literal. See ``docs/300-substrate/oscillator-depth.md``.
"""
from __future__ import annotations

import math

# Address base and outward-weight base. φ = (1 + sqrt(5)) / 2.
PHI = (1.0 + math.sqrt(5.0)) / 2.0

# Recovery scale. Same stored value as the Apollo healing factor.
HEALING = 39.5

# Phase per debt quantum.
MAGNETIC_PHASE = 5.116


def outward_weight(scale: float = 1.0) -> float:
    """Outward between-level weight.

    The unit weight is φ^{-1}. ``scale`` multiplies it. The default
    scale is 1, so the result is φ^{-1}, the same weight the depth-2
    field uses. Pass ``HEALING`` (or any other finite scale) to apply
    the recovery scale without editing ``KuramotoField``.
    """
    s = float(scale)
    if not math.isfinite(s):
        raise ValueError("scale must be finite")
    unit = float(PHI ** -1)
    if s == 1.0:
        return unit
    return unit * s


__all__ = [
    "PHI",
    "HEALING",
    "MAGNETIC_PHASE",
    "outward_weight",
]
