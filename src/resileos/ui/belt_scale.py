"""Belt scale: matrix control for the visual path.

Each named scale selects a frame and an orientation. The proportion is
``resileos.substrate.suite_constants.PHI``, the same φ the oscillator,
Titanos ingest, and the inter-frame motion scale (MAGNETIC_PHASE / PHI)
already use. At belt index L the address weight is φ^{-L}, the same
ladder KuramotoField and ingest use for a level. This module never
builds an image, never calls learn, and never writes a scar.

Scales, outward:

    scale            frame  orientation   belt (index)
    local            3      edge          0
    sun_earth_moon   5      near_triad    1
    orion            9      outer_mark    2
    north_star       12     pole          3

``matrix_control("orion")`` returns belt 2, frame 9. Here ``belt`` is
the scale's index in this list, not the 5-mod Human Belt in
``resileos.ui.five_pin`` (that belt is always 5). The two words are
not interchangeable. The name ``local`` is also different: in
five_pin it is the hub pin at frame 5; here it is the edge scale at
frame 3.
"""
from __future__ import annotations

from typing import Any

from resileos.substrate.suite_constants import PHI

# Name -> (frame, orientation). Belt is the index in this order.
SCALES: tuple[str, ...] = ("local", "sun_earth_moon", "orion", "north_star")
_SCALE_SPEC: dict[str, dict[str, Any]] = {
    "local": {"frame": 3, "orientation": "edge"},
    "sun_earth_moon": {"frame": 5, "orientation": "near_triad"},
    "orion": {"frame": 9, "orientation": "outer_mark"},
    "north_star": {"frame": 12, "orientation": "pole"},
}


def phi_level_weight(level: int) -> float:
    """φ^{-level}, the existing outward address weight for a cascade level."""
    return float(PHI ** (-int(level)))


def matrix_control(scale: str) -> dict[str, Any]:
    """Return the matrix control for one belt scale.

    The returned ``belt`` is this scale's index (0..3), distinct from
    the 5-mod belt in ``five_pin``. ``proportion`` is the shared core
    ``PHI``. ``phi_weight`` is ``PHI ** (-belt)``. Unknown scales
    raise ``ValueError``.
    """
    try:
        index = SCALES.index(scale)
    except ValueError:
        raise ValueError(f"unknown belt scale: {scale!r}") from None
    spec = _SCALE_SPEC[scale]
    return {
        "scale": scale,
        "belt": index,
        "frame": int(spec["frame"]),
        "orientation": str(spec["orientation"]),
        "proportion": float(PHI),
        "phi_weight": phi_level_weight(index),
    }
