"""State dtype decision. Both widths are valid.

  float32  half storage, product default
  float64  full precision

The engine reads RESILEOS_STATE_DTYPE.
Unset means float32.
Accepted: float32, f32, 32, float64, f64, 64.
"""
from __future__ import annotations

import os

import numpy as np

_WIDTHS = {
    "float32": np.float32,
    "f32": np.float32,
    "32": np.float32,
    "float64": np.float64,
    "f64": np.float64,
    "64": np.float64,
}


def state_dtype():
    raw = os.getenv("RESILEOS_STATE_DTYPE", "float32").strip().lower()
    return _WIDTHS.get(raw, np.float32)


def state_dtype_name() -> str:
    dt = state_dtype()
    return "float64" if dt == np.float64 else "float32"
