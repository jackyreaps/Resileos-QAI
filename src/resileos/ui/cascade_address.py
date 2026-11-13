"""Cascade address: belt -> frame -> residual.

A hierarchical address for world or video state. The 5-pin
construction in ``resileos.ui.five_pin`` uses this helper: the belt
is the 5-mod Human Belt, the frame is taken from the pin, and the
residual token completes the path.
"""
from __future__ import annotations

from typing import Any


def cascade_address(belt: int, frame: int, residual: str) -> dict[str, Any]:
    return {
        "belt": int(belt),
        "frame": int(frame),
        "residual": residual,
        "path": f"{belt}/{frame}/{residual}",
    }


def is_valid_address(addr: dict[str, Any]) -> bool:
    return (
        isinstance(addr.get("belt"), int)
        and isinstance(addr.get("frame"), int)
        and bool(addr.get("residual"))
    )
