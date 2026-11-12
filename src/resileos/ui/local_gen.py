"""Local generator driven by the Kuramoto field.

Uses:
  - resileos.substrate.oscillator.KuramotoField (when the package is present)
  - residual address from the frame
  - local pattern from the field state

No external provider. Scaffold for larger exposure and guild formalization.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address


def _kuramoto_field():
    try:
        from resileos.substrate.oscillator import KuramotoField
    except ImportError:
        return None
    return KuramotoField


def field_from_embed(embed: dict[str, Any]) -> dict[str, Any]:
    """Drive a small Kuramoto field from the residual address, or a fallback."""
    KuramotoField = _kuramoto_field()
    if KuramotoField is not None:
        # three oscillators, one per mask bit family
        field = KuramotoField(3)
        theta0 = np.array([
            embed["mean_luma"] * np.pi,
            embed["edge_density"] * np.pi,
            (embed["belt"] % 3) * 0.5,
        ])
        field.theta = theta0
        field.step(epsilon=1.0)
        return {
            "backend": "kuramoto",
            "theta": [round(float(x), 4) for x in field.theta],
            "n": 3,
        }
    # fallback when the package is not importable in this environment
    return {
        "backend": "fallback",
        "theta": [
            round(embed["mean_luma"] * 3.1416, 4),
            round(embed["edge_density"] * 3.1416, 4),
            round((embed["belt"] % 3) * 0.5, 4),
        ],
        "n": 3,
    }


def local_pattern_from_theta(theta: list[float], size: int = 32) -> np.ndarray:
    """Cheap local pattern from oscillator phases. No external call."""
    rng = np.random.default_rng(int(abs(sum(theta)) * 1000) % (2**32))
    base = rng.random((size, size, 3)).astype(np.float32)
    # phase tint
    for c, ph in enumerate(theta[:3]):
        base[:, :, c] *= 0.5 + 0.5 * abs(np.sin(ph))
    return (np.clip(base, 0, 1) * 255).astype(np.uint8)


def generate_local(
    arr: np.ndarray | None = None,
    *,
    belt: int = 0,
    frame: int = 0,
    subject: str = "frame",
    persona: str = "",
) -> dict[str, Any]:
    """Local generation using the scale address (residual + Kuramoto + gate)."""
    if arr is None:
        arr = np.zeros((8, 8, 3), dtype=np.uint8)
    scaled = scale_address(arr, belt=belt, frame=frame, persona=persona, subject=subject)
    pattern = local_pattern_from_theta(scaled["field"]["theta"])
    return {
        "embed": scaled["embed"],
        "field": scaled["field"],
        "triple": scaled["triple"],
        "gate": scaled["gate"],
        "pattern_shape": list(pattern.shape),
        "pattern": pattern,
        "backend": scaled["field"]["backend"],
        "note": "Local. Scale address shared with facts and world state.",
    }
