"""Perception to control.

Image, video, audio, text, and art all write into Psyche the same way.
Recesses are a later encoding. Until then, the perception address is the input.
"""
from __future__ import annotations

from typing import Any

from resileos.kin.psyche import Psyche


def perceive_into(psyche: Psyche, perceived: dict[str, Any], *, drive: str = "endocrine") -> dict[str, Any]:
    """One path for image, video, audio, text, or art."""
    psyche.write_perception(perceived)
    val = perceived.get("mean_luma") or perceived.get("energy") or perceived.get("motion") or 0.0
    psyche.set_drives({drive: float(val) if isinstance(val, (int, float)) else 0.0})
    return psyche.state
