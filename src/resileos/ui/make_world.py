"""Make: still or clip saved under a world hub with a scale address.

Continue loads that address and extends.
Scene rows make a world queryable.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from resileos.ui.local_gen import generate_local
from resileos.ui.scale_address import scale_address
from resileos.ui.video_gen import request_video, video_status


def scene_rows(world_id: str, look: str, address: dict[str, Any]) -> list[dict[str, str]]:
    sub = world_id if world_id.startswith("world:") else f"world:{world_id}"
    obj = f"belt{address.get('belt')}_frame{address.get('frame')}_{address.get('residual_bin')}"
    return [
        {"subject": sub, "relation": "has_scene", "obj": look[:80]},
        {"subject": sub, "relation": "looks_like", "obj": look[:80]},
        {"subject": sub, "relation": "address", "obj": obj},
    ]


def make_still(
    prompt: str,
    *,
    world_id: str = "world:default",
    belt: int = 0,
    frame: int = 0,
    persona: str = "",
) -> dict[str, Any]:
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    out = generate_local(arr, belt=belt, frame=frame, subject=world_id, persona=persona)
    rows = scene_rows(world_id, prompt, out["embed"])
    return {
        "kind": "still",
        "prompt": prompt,
        "world_id": world_id,
        "address": out["embed"],
        "pattern_shape": out["pattern_shape"],
        "rows": rows,
        "backend": out["backend"],
    }


def make_clip(prompt: str, *, world_id: str = "world:default") -> dict[str, Any]:
    status = video_status()
    if not status.get("configured"):
        still = make_still(prompt, world_id=world_id)
        still["kind"] = "clip_unconfigured"
        still["note"] = "Video provider not set. Still and address saved."
        return still
    vid = request_video(prompt)
    addr = scale_address(subject=world_id)
    return {
        "kind": "clip",
        "prompt": prompt,
        "world_id": world_id,
        "address": addr["embed"],
        "video": vid,
        "rows": scene_rows(world_id, prompt, addr["embed"]),
    }


def continue_from(address: dict[str, Any], prompt: str, *, world_id: str = "world:default") -> dict[str, Any]:
    """Next piece uses the stored belt/frame and steps the frame."""
    belt = int(address.get("belt", 0))
    frame = int(address.get("frame", 0)) + 1
    return make_still(prompt, world_id=world_id, belt=belt, frame=frame)
