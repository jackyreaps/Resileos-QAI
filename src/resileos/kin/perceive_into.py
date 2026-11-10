"""Perception to control.

Image, video, audio, text, and art all write into Psyche the same way.
Recesses are a later encoding. Until then, the perception address is the input.
"""
from __future__ import annotations

from typing import Any

from resileos.kin.psyche import Psyche


def perception_scalar(perceived: dict[str, Any]) -> float:
    """Drive scalar. 0.0 is a real value. Video prefers motion over luma."""
    for key in ("motion", "mean_luma", "energy", "tokens"):
        if key not in perceived or perceived[key] is None:
            continue
        try:
            return float(perceived[key])
        except (TypeError, ValueError):
            continue
    return 0.0


def perceive_into(psyche: Psyche, perceived: dict[str, Any], *, drive: str = "endocrine") -> dict[str, Any]:
    """One path for image, video, audio, text, or art."""
    psyche.write_perception(perceived)
    psyche.set_drives({drive: perception_scalar(perceived)})
    return psyche.state
