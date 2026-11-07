"""Shared core, field, search, and phasor for the process.

step_shared runs the residual core.
search_shared builds an oscillator-oriented search from the field.
phasor_shared sets one edge on a PhasorGraph.
"""
from __future__ import annotations

from typing import Any

import numpy as np

_SHARED: dict[str, Any] = {
    "core": None, "field": None, "phasor": None,
    "ready": False, "steps": 0,
}


def init_shared() -> dict[str, Any]:
    global _SHARED
    try:
        from resileos.core import CoreConfig, ResidualCore
        _SHARED["core"] = ResidualCore(CoreConfig(m=4, n=4, r=2, n_residual_layers=2), seed=0)
    except Exception:
        _SHARED["core"] = None
    try:
        from resileos.substrate.oscillator import KuramotoField
        _SHARED["field"] = KuramotoField(n=3)
    except Exception:
        _SHARED["field"] = None
    try:
        from resileos.substrate.phasor import PhasorGraph
        _SHARED["phasor"] = PhasorGraph(n_nodes=4)
    except Exception:
        _SHARED["phasor"] = None
    _SHARED["ready"] = True
    _SHARED["steps"] = 0
    return _SHARED


def get_shared() -> dict[str, Any]:
    if not _SHARED["ready"]:
        return init_shared()
    return _SHARED


def step_shared(seed_value: float = 0.5) -> dict[str, Any]:
    shared = get_shared()
    core = shared.get("core")
    shared["steps"] = shared.get("steps", 0) + 1
    if core is None:
        return {"backend": "fallback", "steps": shared["steps"]}
    packet = core.step(np.eye(4) * (0.5 + float(seed_value)))
    return {
        "backend": "residual_core",
        "steps": shared["steps"],
        "packet": packet.to_dict() if hasattr(packet, "to_dict") else "packet",
    }


def search_shared() -> dict[str, Any]:
    shared = get_shared()
    field = shared.get("field")
    try:
        from resileos.evolution_oscillator import OscillatorOrientedSearch
        search = OscillatorOrientedSearch(field=field, budget=8, seed=0)
        return {"backend": "oscillator_search", "budget": search.budget}
    except Exception:
        return {"backend": "fallback", "budget": 0}


def phasor_shared(phase: float = 0.0) -> dict[str, Any]:
    shared = get_shared()
    g = shared.get("phasor")
    if g is None:
        return {"backend": "fallback", "edges": 0}
    g.set_edge(0, 1, amplitude=1.0, phase=phase)
    return {"backend": "phasor", "edges": g.n_edges()}
