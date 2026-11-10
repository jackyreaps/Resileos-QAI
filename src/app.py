"""Editable-install shim for the repo-root ``app`` module.

A src-layout editable install only puts ``src/`` on ``sys.path``, so
``py-modules`` entries that live at the repository root are not
importable. This module loads that root file by path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[1] / "app.py"
_spec = importlib.util.spec_from_file_location("_resileos_app_impl", _IMPL)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {_IMPL}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_resileos_app_impl"] = _mod
_spec.loader.exec_module(_mod)
sys.modules["app"] = _mod
