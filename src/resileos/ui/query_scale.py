"""Attach scale address and core step to a query response."""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address
from resileos.ui.shared_state import get_shared


def with_scale(response: dict[str, Any], subject: str, relation: str) -> dict[str, Any]:
    """Add scale, core, and search to an existing query response."""
    shared = get_shared()
    addr = scale_address(
        np.zeros((8, 8, 3), dtype=np.uint8),
        belt=0,
        frame=0,
        subject=subject,
    )
    response["scale"] = {
        "address": addr["embed"],
        "gate": addr["gate"],
        "field": addr["field"],
        "core": addr.get("core"),
        "search": addr.get("search"),
        "shared_core": shared["core"] is not None,
        "shared_field": shared["field"] is not None,
    }
    return response
