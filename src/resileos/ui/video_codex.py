"""Video from a base codex compressed into scaling recesses.

A recess is a scale address that can hold a frame or a short sequence.
The base codex is a prompt or fact list. Continuity comes from stepping
the frame on the same belt.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address
from resileos.ui.make_world import scene_rows


def recess_from_codex(
    codex: str,
    *,
    world_id: str = "world:video",
    belt: int = 0,
    n_frames: int = 4,
) -> dict[str, Any]:
    """Compress a codex into a sequence of recess addresses."""
    recesses = []
    for i in range(n_frames):
        addr = scale_address(
            np.zeros((8, 8, 3), dtype=np.uint8),
            belt=belt,
            frame=i,
            subject=world_id,
            step_core=False,
        )
        recesses.append({
            "frame": i,
            "address": addr["embed"],
            "gate": addr["gate"],
        })
    rows = scene_rows(world_id, codex[:80], recesses[0]["address"])
    return {
        "codex": codex,
        "world_id": world_id,
        "recesses": recesses,
        "rows": rows,
        "note": "Each recess is a scale address. Continue steps the frame.",
    }


def continue_recess(
    last_recess: dict[str, Any],
    codex: str,
    *,
    world_id: str = "world:video",
) -> dict[str, Any]:
    """Extend from the last recess address."""
    belt = int(last_recess.get("belt", 0))
    frame = int(last_recess.get("frame", 0)) + 1
    return recess_from_codex(codex, world_id=world_id, belt=belt, n_frames=1)
