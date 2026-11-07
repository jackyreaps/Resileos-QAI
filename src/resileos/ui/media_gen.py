"""Media generation helpers for the portable Studio surface.

Providers are optional. Pollinations is the zero-key default for stills.
Video is a separate, optional path — labeled, not claimed as a Higgsfield equivalent.
"""
from __future__ import annotations

import os
from urllib.parse import quote


def still_url(prompt: str, width: int = 1024, height: int = 1024) -> str:
    """Pollinations still URL. No API key required for the public endpoint."""
    base = os.getenv("RESILEOS_IMAGE_API_URL", "https://image.pollinations.ai/prompt")
    return f"{base}/{quote(prompt)}?width={width}&height={height}&nologo=true"


def video_available() -> bool:
    """True only if an explicit video provider is configured."""
    return bool(os.getenv("RESILEOS_VIDEO_PROVIDER", "").strip())


def video_status() -> str:
    if video_available():
        return "configured"
    return "not configured — stills only; video provider not set"
