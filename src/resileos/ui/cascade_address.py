"""Cascade address scaffold.

A hierarchical address for world or video state:
  belt -> frame -> residual

This is the shape Genesis world-building and video embedding
can share later. The values are placeholders until the suite
quantities are coded.
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
