"""Fluid generator: residual address + persona + cheap still/video hooks.

Ties existing pieces:
  - residual_embed for a stable address
  - media_gen for stills (Pollinations, no GPU)
  - video_gen for optional video
  - user profile persona when present

Not a foundation model. A scaffold that stays cheap and consistent
because the address is stable and the provider is a peripheral.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.media_gen import still_url
from resileos.ui.residual_embed import address_triple, embed_frame
from resileos.ui.video_gen import request_video, video_status


def fluid_prompt(embed: dict[str, Any], persona: str = "") -> str:
    """Build a short prompt from the residual address and optional persona."""
    base = (
        f"belt {embed['belt']} frame {embed['frame']} "
        f"residual {embed['residual_bin']} luma {embed['mean_luma']}"
    )
    if persona:
        return f"{persona}, {base}"
    return base


def generate_still(
    arr: np.ndarray | None = None,
    *,
    belt: int = 0,
    frame: int = 0,
    persona: str = "",
    subject: str = "frame",
) -> dict[str, Any]:
    """Produce a still URL and the residual triple. No local GPU."""
    if arr is None:
        arr = np.zeros((8, 8, 3), dtype=np.uint8)
    embed = embed_frame(arr, belt=belt, frame=frame)
    prompt = fluid_prompt(embed, persona)
    return {
        "embed": embed,
        "triple": address_triple(embed, subject=subject),
        "prompt": prompt,
        "still_url": still_url(prompt),
        "backend": "pollinations",
    }


def generate_video_hook(prompt: str) -> dict[str, Any]:
    """Video only when a provider returns an asset. Otherwise UNAVAILABLE.

    No placeholder URL is invented.
    """
    unavailable = {
        "status": "UNAVAILABLE",
        "detail": "No video generator is configured on this host.",
        "draft": False,
        "prompt": prompt,
        "url": None,
    }
    if not video_status()["configured"]:
        return unavailable
    result = request_video(prompt)
    url = None
    payload = result.get("result")
    if isinstance(payload, dict):
        url = payload.get("url") or payload.get("video_url")
    if result.get("status") != "submitted" or not url:
        unavailable["detail"] = "Video provider returned no asset."
        return unavailable
    return {
        "status": "submitted",
        "detail": "",
        "draft": False,
        "prompt": prompt,
        "url": url,
        "result": payload,
    }
