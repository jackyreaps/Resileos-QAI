"""Public residual label.

The body is a placeholder. A private implementation can replace it
without changing callers.

Set RESILEOS_RESIDUAL_IMPL to "package.module:function"
to load a private residual. The function signature is:

    fn(mean_luma: float, edge_density: float, belt: int) -> str

If unset or the import fails, the placeholder label is used.
"""
from __future__ import annotations

import importlib
import os


def _placeholder(mean_luma: float, edge_density: float, belt: int) -> str:
    luma_hi = mean_luma > 0.5
    edge_hi = edge_density > 0.15
    return f"r{int(luma_hi)}{int(edge_hi)}_s{int(belt) % 4}"


def suite_residual(mean_luma: float, edge_density: float, belt: int = 0) -> str:
    target = os.getenv("RESILEOS_RESIDUAL_IMPL", "").strip()
    if not target or ":" not in target:
        return _placeholder(mean_luma, edge_density, belt)
    mod_name, fn_name = target.rsplit(":", 1)
    try:
        fn = getattr(importlib.import_module(mod_name), fn_name)
        return str(fn(mean_luma, edge_density, int(belt)))
    except Exception:
        return _placeholder(mean_luma, edge_density, belt)
