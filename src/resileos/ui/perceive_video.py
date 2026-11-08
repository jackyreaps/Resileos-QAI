"""Video perception.

Perceives a short stack of frames with the same diagnostics used for stills
and attaches the scale address so a clip can enter the hub.
"""
from __future__ import annotations

from typing import Any, Optional

from typing import Any

import numpy as np

from resileos.ui.diagnostics import diagnose_image
from resileos.ui.scale_address import scale_address


def perceive_video(
    frames: np.ndarray,
    *,
    subject: str = "video",
    fps: float = 12.0,
) -> dict[str, Any]:
    """Perceive a clip: per-frame diagnostics plus scale address.

    frames: T x H x W or T x H x W x C.
    """
    f = np.asarray(frames)
    if f.ndim == 3:
        f = f[..., None]
    if f.ndim != 4:
        f = f.reshape(1, *f.shape)
    t = f.shape[0]
    diags = [diagnose_image(f[i]) for i in range(min(t, 8))]
    mean_luma = float(np.mean([d["mean_luma"] for d in diags])) if diags else 0.0
    mean_edge = float(np.mean([d["edge_density"] for d in diags])) if diags else 0.0
    # motion proxy: mean absolute frame difference
    if t > 1:
        diffs = [float(np.mean(np.abs(f[i].astype(np.float32) - f[i - 1].astype(np.float32)))) for i in range(1, min(t, 8))]
        motion = float(np.mean(diffs))
    else:
        motion = 0.0
    addr = scale_address(f[0], subject=subject)
    return {
        "subject": subject,
        "frames": int(t),
        "fps": float(fps),
        "duration_s": round(float(t) / max(0.1, fps), 3),
        "mean_luma": round(mean_luma, 4),
        "mean_edge": round(mean_edge, 4),
        "motion": round(motion, 4),
        "address": addr["embed"],
        "gate": addr["gate"],
        "sample_diagnostics": diags[:2],
    }

def into_kin(perceived: dict, psyche=None):
    """Send this perception into Psyche and Athena."""
    from resileos.kin.psyche import Psyche
    from resileos.kin.wire_perception import wire_perception
    return wire_perception(psyche or Psyche(), perceived)
