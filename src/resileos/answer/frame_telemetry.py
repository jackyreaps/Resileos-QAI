"""Process-level truth-frame histogram (production telemetry).

Facts in the store do not carry frame_assignment; frames are assigned at
*answer time*. Counters live on the process so /stats can report the
distribution of claim types the Oracle has emitted.
"""
from __future__ import annotations

from threading import Lock
from typing import Dict

_LOCK = Lock()
_COUNTS: Dict[str, int] = {
    "exact": 0,
    "reconstructed": 0,
    "abstained": 0,
    "unresolved": 0,
    "answered": 0,
    "no_rows": 0,
    "none_channel": 0,
}


def record_frame(frame: str, status: str = "") -> None:
    """Increment histogram for a completed /answer (or tools execute)."""
    f = (frame or "unresolved").lower()
    st = (status or "").upper()
    with _LOCK:
        if f in _COUNTS:
            _COUNTS[f] += 1
        else:
            _COUNTS[f] = 1
        if st == "ANSWERED":
            _COUNTS["answered"] += 1
        elif st == "NO_ROWS":
            _COUNTS["no_rows"] += 1
        elif st == "NONE_CHANNEL":
            _COUNTS["none_channel"] += 1
        elif st == "ABSTAINED":
            _COUNTS["abstained"] = _COUNTS.get("abstained", 0)  # already via frame


def frame_histogram() -> dict:
    with _LOCK:
        return dict(_COUNTS)


def reset_frame_histogram() -> None:
    with _LOCK:
        for k in list(_COUNTS.keys()):
            _COUNTS[k] = 0
