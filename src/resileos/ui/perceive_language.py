"""Language perception.

Scores a short text for length, token estimate, and script mix,
and attaches the scale address. This is not a translator.
It is the surface that lets text enter the hub like image and audio.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address


def perceive_language(text: str, *, subject: str = "text") -> dict[str, Any]:
    """Perceive text: length, token estimate, script shares, scale address."""
    s = text or ""
    n = len(s)
    tokens = len(s.split()) if s.strip() else 0
    latin = sum(1 for c in s if "A" <= c <= "Z" or "a" <= c <= "z")
    other = sum(1 for c in s if ord(c) > 127)
    # pad to a 2-D frame with both axes long enough for np.gradient
    arr = np.array([ord(c) % 256 for c in s[:256]], dtype=np.float32)
    if arr.size < 8:
        arr = np.resize(arr if arr.size else np.zeros(1), 8)
    frame = arr.reshape(-1, 1)
    frame = np.hstack([frame, frame])
    addr = scale_address(frame, subject=subject)
    return {
        "subject": subject,
        "chars": n,
        "tokens": tokens,
        "latin_share": round(latin / max(1, n), 3),
        "other_share": round(other / max(1, n), 3),
        "address": addr["embed"],
        "gate": addr["gate"],
        "note": "perception only; not a translation",
    }
