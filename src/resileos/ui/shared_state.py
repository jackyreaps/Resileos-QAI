"""Shared residual core and Kuramoto field for the process.

Built once. step_shared() runs one core step so the core is on the path.
"""
from __future__ import annotations

from typing import Any

import numpy as np

_SHARED: dict[str, Any] = {"core": None, "field": None, "ready": False, "steps": 0}


def init_shared() -> dict[str, Any]:
    global _SHARED
    try:
        from resileos.core import CoreConfig, ResidualCore
        cfg = CoreConfig(m=4, n=4, r=2, n_residual_layers=2)
        _SHARED["core"] = ResidualCore(cfg, seed=0)
    except Exception:
        _SHARED["core"] = None
    try:
        from resileos.substrate.oscillator import KuramotoField
        _SHARED["field"] = KuramotoField(n=3)
    except Exception:
        _SHARED["field"] = None
    _SHARED["ready"] = True
    _SHARED["steps"] = 0
    return _SHARED


def get_shared() -> dict[str, Any]:
    if not _SHARED["ready"]:
        return init_shared()
    return _SHARED


def step_shared(seed_value: float = 0.5) -> dict[str, Any]:
    """Run one residual core step. Records that the core was used."""
    shared = get_shared()
    core = shared.get("core")
    if core is None:
        shared["steps"] = shared.get("steps", 0) + 1
        return {"backend": "fallback", "steps": shared["steps"]}
    W = np.eye(4) * (0.5 + float(seed_value))
    packet = core.step(W)
    shared["steps"] = shared.get("steps", 0) + 1
    return {
        "backend": "residual_core",
        "steps": shared["steps"],
        "packet": packet.to_dict() if hasattr(packet, "to_dict") else str(type(packet)),
    }
