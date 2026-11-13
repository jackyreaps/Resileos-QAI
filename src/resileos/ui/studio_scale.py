"""Studio diagnostics addition.

In the Diagnostics tab, after the histogram, add:

    from resileos.ui.scale_address import scale_address
    addr = scale_address(img, subject="uploaded_photo", step_core=False)
    st.write("Scale gate:", addr["gate"]["frame"])
    st.json({"core": addr.get("core"), "search": addr.get("search")})

This file is the helper the tab can call if you prefer an import.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address


def diagnose_with_scale(arr: np.ndarray, subject: str = "uploaded_photo") -> dict[str, Any]:
    addr = scale_address(arr, subject=subject, step_core=False)
    return {
        "gate": addr["gate"]["frame"],
        "address": addr["embed"],
        "core": addr.get("core"),
        "search": addr.get("search"),
    }
