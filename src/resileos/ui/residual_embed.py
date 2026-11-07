"""Residual embedding scaffold.

Projects a frame or short sequence into a residual coordinate
that the store can gate. This is scaffolding for later hardware
or software encoding. It does not claim to implement the full
cascade or the oscillating engine.

The coordinate is a stable address:
  belt, frame, residual_bin, debt

Later encoders replace the feature function. The address shape stays.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.suite_residual import suite_residual


def residual_bin(mean_luma: float, edge_density: float) -> str:
    """Coarse residual bin from two scalars. Placeholder for the suite residual."""
    if edge_density > 0.2 and mean_luma > 0.5:
        return "high_high"
    if edge_density > 0.2:
        return "high_low"
    if mean_luma > 0.5:
        return "low_high"
    return "low_low"


def embed_frame(arr: np.ndarray, *, belt: int = 0, frame: int = 0) -> dict[str, Any]:
    """Embed one frame into a residual address.

    arr: HxW or HxWxC
    """
    if arr.ndim == 3:
        gray = arr[..., :3].astype(np.float32)
        if gray.max() > 1.5:
            gray = gray / 255.0
        gray = 0.2126 * gray[..., 0] + 0.7152 * gray[..., 1] + 0.0722 * gray[..., 2]
    else:
        gray = arr.astype(np.float32)
        if gray.max() > 1.5:
            gray = gray / 255.0
    gy, gx = np.gradient(gray)
    edge = float((np.hypot(gx, gy) > 0.08).mean())
    luma = float(gray.mean())
    rbin = suite_residual(luma, edge, belt)
    return {
        "belt": int(belt),
        "frame": int(frame),
        "residual_bin": rbin,
        "mean_luma": round(luma, 4),
        "edge_density": round(edge, 4),
        "debt": 1.0,
        "note": "Scaffold address. Replace residual_bin with suite residual when coded.",
    }


def address_triple(embed: dict[str, Any], subject: str = "frame") -> dict[str, str]:
    """Triple the gate can accept or reject."""
    obj = f"belt{embed['belt']}_frame{embed['frame']}_{embed['residual_bin']}"
    return {"subject": subject, "relation": "residual_address", "obj": obj}
