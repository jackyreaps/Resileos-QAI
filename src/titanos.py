"""Editable-install shim for the repo-root ``titanos`` module.

See ``src/app.py``. The implementation is ``titanos.py`` at the
repository root, which loads ``scripts/titanos.py``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[1] / "titanos.py"
_spec = importlib.util.spec_from_file_location("_resileos_titanos_root", _IMPL)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {_IMPL}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_resileos_titanos_root"] = _mod
_spec.loader.exec_module(_mod)
sys.modules["titanos"] = _mod
