"""Image perception.

Uses diagnostics for real figures and attaches the scale address
so a perceived image can enter the hub and the Apollo path.
"""
from __future__ import annotations

from typing import Any, Optional

from typing import Any

import numpy as np

from resileos.ui.diagnostics import diagnose_image
from resileos.ui.frame_codec import codec_summary, encode_frame
from resileos.ui.scale_address import scale_address


def perceive_image(arr: np.ndarray, *, subject: str = "image") -> dict[str, Any]:
    """Perceive an image: diagnostics, core residual, and scale address."""
    image = np.asarray(arr)
    diag = diagnose_image(image)
    coded = encode_frame(image)
    addr = scale_address(image, subject=subject, step_core=False)
    embed = dict(addr["embed"])
    embed["residual_bin"] = coded["residual_bin"]
    embed["reconstruction_mse"] = round(coded["mse"], 6)
    embed["note"] = (
        "residual_bin is ResidualCore relative reconstruction error "
        "on a grayscale projection, not the luma/edge scaffold."
    )
    return {
        "subject": subject,
        "diagnostics": diag,
        "address": embed,
        "gate": addr["gate"],
        "mean_luma": diag.get("mean_luma"),
        "edge_density": diag.get("edge_density"),
        "codec": codec_summary(coded),
    }

def into_kin(perceived: dict, psyche=None):
    """Send this perception into Psyche and Athena."""
    from resileos.kin.psyche import Psyche
    from resileos.kin.wire_perception import wire_perception
    return wire_perception(psyche or Psyche(), perceived)
