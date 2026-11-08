"""Optional video path.

Video is a peripheral, like the mouth. It is not the record.
A provider is required. Without one, the status is not configured.

This is not a claim of Higgsfield-class generation. It is the
hook the Studio can call when a provider is set.
"""
from __future__ import annotations

from resileos.ui.scale_address import scale_address

import os
from typing import Any, Optional


def video_provider() -> str:
    return os.getenv("RESILEOS_VIDEO_PROVIDER", "").strip()


def video_status() -> dict[str, Any]:
    p = video_provider()
    return {
        "configured": bool(p),
        "provider": p or None,
        "note": "Stills are available without a provider. Video requires one.",
    }


def request_video(prompt: str, *, provider_fn: Optional[Any] = None) -> dict[str, Any]:
    """Request a video. Returns a status, not a silent invention.

    provider_fn(prompt) -> dict with at least a url or job id.
    """
    if not video_provider() and provider_fn is None:
        return {"status": "not_configured", "prompt": prompt, "url": None}
    if provider_fn is None:
        return {"status": "provider_set_but_no_fn", "prompt": prompt, "url": None}
    result = provider_fn(prompt)
    return {"status": "submitted", "prompt": prompt, "result": result}

def video_address(prompt: str, world_id: str = "world:video") -> dict:
    addr = scale_address(subject=world_id)
    return {"prompt": prompt, "world_id": world_id, "address": addr["embed"]}
