"""Wire scale address into task and perceive responses.

One address for a step, a frame, or a world state.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from resileos.ui.scale_address import scale_address


def task_with_scale(
    goal: str,
    steps: list[dict[str, str]],
    ask,
    *,
    persona: str = "",
    belt: int = 0,
) -> dict[str, Any]:
    """Run lookups and attach a scale address to the trace."""
    from resileos.ui.task_api import task_from_steps

    result = task_from_steps(goal, steps, ask)
    # address for the goal itself
    addr = scale_address(
        np.zeros((8, 8, 3), dtype=np.uint8),
        belt=belt,
        frame=0,
        persona=persona,
        subject=goal[:40] or "goal",
    )
    result["scale"] = {
        "address": addr["embed"],
        "gate": addr["gate"],
        "field": addr["field"],
    }
    return result


def perceive_with_scale(
    arr: np.ndarray,
    *,
    subject: str = "image",
    persona: str = "",
    belt: int = 0,
    frame: int = 0,
) -> dict[str, Any]:
    """Image features plus the shared scale address."""
    from resileos.ui.perceive_image import perceive_image

    base = perceive_image(arr, subject=subject)
    addr = scale_address(arr, belt=belt, frame=frame, persona=persona, subject=subject)
    triple = addr.get("triple") or {
        "subject": subject,
        "relation": "residual_address",
        "obj": str(addr["embed"].get("residual_bin", "")),
    }
    base["candidates"] = [{
        "triple": triple,
        "accepted": False,
        "note": "Not a fact until eat accepts and learn is called.",
    }]
    base["scale"] = {
        "address": addr["embed"],
        "gate": addr["gate"],
        "field": addr["field"],
    }
    return base
