"""Portable photo diagnostics for Studio / Chat / later Genesis hosts.

Produces simple, honest figures from an uploaded image:
  - luminance histogram
  - RGB channel means
  - edge-density estimate
  - basic size / aspect

No medical or forensic claims. These are work figures for inspection.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def diagnose_image(arr: np.ndarray) -> dict[str, Any]:
    """Return metrics and a small histogram payload for an RGB or gray array.

    arr: HxW or HxWxC uint8 or float in [0, 1].
    """
    if arr.ndim == 2:
        gray = arr.astype(np.float32)
        rgb = None
    else:
        rgb = arr[..., :3].astype(np.float32)
        if rgb.max() > 1.5:
            rgb = rgb / 255.0
        gray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

    if gray.max() > 1.5:
        gray = gray / 255.0

    hist, edges = np.histogram(gray.ravel(), bins=32, range=(0.0, 1.0))
    # crude edge density via gradient magnitude
    gy, gx = np.gradient(gray)
    mag = np.hypot(gx, gy)
    edge_density = float((mag > 0.08).mean())

    out: dict[str, Any] = {
        "height": int(gray.shape[0]),
        "width": int(gray.shape[1]),
        "aspect": round(float(gray.shape[1]) / max(1, gray.shape[0]), 3),
        "mean_luma": round(float(gray.mean()), 4),
        "std_luma": round(float(gray.std()), 4),
        "edge_density": round(edge_density, 4),
        "histogram": {
            "bins": [round(float(x), 4) for x in edges[:-1]],
            "counts": [int(c) for c in hist],
        },
    }
    if rgb is not None:
        out["channel_means"] = {
            "r": round(float(rgb[..., 0].mean()), 4),
            "g": round(float(rgb[..., 1].mean()), 4),
            "b": round(float(rgb[..., 2].mean()), 4),
        }
    return out


def histogram_rows(diag: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows suitable for st.bar_chart or a simple table."""
    h = diag.get("histogram") or {}
    bins = h.get("bins") or []
    counts = h.get("counts") or []
    return [{"bin": b, "count": c} for b, c in zip(bins, counts)]
