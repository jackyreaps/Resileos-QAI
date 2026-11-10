"""Editable-install shim for the repo-root ``run_hybrid`` module."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[1] / "run_hybrid.py"
_spec = importlib.util.spec_from_file_location("_resileos_run_hybrid_impl", _IMPL)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {_IMPL}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_resileos_run_hybrid_impl"] = _mod
_spec.loader.exec_module(_mod)
sys.modules["run_hybrid"] = _mod
