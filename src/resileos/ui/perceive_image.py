"""Image perception.

Uses diagnostics for real figures and attaches the scale address
so a perceived image can enter the hub and the Apollo path.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.diagnostics import diagnose_image
from resileos.ui.scale_address import scale_address


def perceive_image(arr: np.ndarray, *, subject: str = "image") -> dict[str, Any]:
    """Perceive an image: diagnostics plus scale address."""
    diag = diagnose_image(np.asarray(arr))
    addr = scale_address(
        np.asarray(arr),
        subject=subject,
    )
    return {
        "subject": subject,
        "diagnostics": diag,
        "address": addr["embed"],
        "gate": addr["gate"],
        "mean_luma": diag.get("mean_luma"),
        "edge_density": diag.get("edge_density"),
    }
