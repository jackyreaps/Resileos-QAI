"""Endocrine drives.

Scalable control signals from perception. Psyche holds them. Athena reads them.
Image, video, audio, text, and art use the same path until coded recesses exist.
"""
from __future__ import annotations

from typing import Any

# Drive names inherited from the docs. Not derived here.
DRIVES = ("endocrine", "pineal", "flashpoint", "otx", "gbx", "ultradian")


def default_drives() -> dict[str, float]:
    return {k: 0.0 for k in DRIVES}


def update_drives(state: dict[str, float], signal: dict[str, float]) -> dict[str, float]:
    """Merge a signal into the drive state. Unknown keys are ignored."""
    out = dict(state)
    for k, v in signal.items():
        if k in DRIVES:
            out[k] = float(v)
    return out


def drive_rows(subject: str, drives: dict[str, float]) -> list[dict[str, str]]:
    return [
        {"subject": subject, "relation": f"drive_{k}", "obj": str(round(float(drives.get(k, 0.0)), 4))}
        for k in DRIVES
    ]
