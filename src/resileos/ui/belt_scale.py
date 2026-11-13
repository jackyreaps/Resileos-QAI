"""Belt scale: matrix control for the visual path.

The same pentagram figure is used at every scale, with phi as the
proportion. Only the frame changes. This module never builds an image,
never calls learn, and never writes a scar.

Scales, outward, with their frame and orientation:

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


def matrix_control(scale: str) -> dict[str, Any]:
    """Return the matrix control for one belt scale.

    The returned ``belt`` is this scale's index (0..3), distinct from
    the 5-mod belt in ``five_pin``. Unknown scales raise ``ValueError``.
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
    }
