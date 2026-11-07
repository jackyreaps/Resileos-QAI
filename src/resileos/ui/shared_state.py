"""Shared residual core and Kuramoto field for the process.

Built once at startup. Routes and Studio call get_shared().
"""
from __future__ import annotations

from typing import Any, Optional

_SHARED: dict[str, Any] = {"core": None, "field": None, "ready": False}


def init_shared() -> dict[str, Any]:
    """Create one ResidualCore and one KuramotoField if the package is present."""
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
    return _SHARED


def get_shared() -> dict[str, Any]:
    if not _SHARED["ready"]:
        return init_shared()
    return _SHARED
