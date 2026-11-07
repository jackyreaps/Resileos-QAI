"""Image encoder: pixels to candidate features.

Not a vision foundation model. It extracts measurable features
from an image array so the perception path has a real signal
instead of caption rules alone.

Features:
  - dominant channel
  - mean luma
  - edge density
  - aspect class
"""
from __future__ import annotations

from typing import Any

import numpy as np


def encode_image(arr: np.ndarray) -> dict[str, Any]:
    """Encode an RGB or gray array into a feature dict."""
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

    gy, gx = np.gradient(gray)
    edge = float((np.hypot(gx, gy) > 0.08).mean())
    h, w = gray.shape[:2]
    aspect = float(w) / max(1, h)

    dominant = "gray"
    if rgb is not None:
        means = rgb.mean(axis=(0, 1))
        names = ["red", "green", "blue"]
        dominant = names[int(np.argmax(means))]

    aspect_class = "wide" if aspect > 1.2 else "tall" if aspect < 0.8 else "square"

    return {
        "height": int(h),
        "width": int(w),
        "aspect": round(aspect, 3),
        "aspect_class": aspect_class,
        "mean_luma": round(float(gray.mean()), 4),
        "edge_density": round(edge, 4),
        "dominant_channel": dominant,
    }


def features_to_triples(features: dict[str, Any], subject: str = "image") -> list[dict[str, str]]:
    """Turn encoder features into candidate triples. Not facts."""
    triples = [
        {"subject": subject, "relation": "aspect_class", "obj": features["aspect_class"]},
        {"subject": subject, "relation": "dominant_channel", "obj": features["dominant_channel"]},
        {"subject": subject, "relation": "edge_density_bin", "obj": "high" if features["edge_density"] > 0.15 else "low"},
    ]
    return triples
