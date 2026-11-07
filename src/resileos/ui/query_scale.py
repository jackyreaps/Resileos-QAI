"""Attach scale, core step, search, and phasor to a query response."""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address
from resileos.ui.shared_state import get_shared, phasor_shared, search_shared, step_shared


def with_scale(response: dict[str, Any], subject: str, relation: str) -> dict[str, Any]:
    shared = get_shared()
    addr = scale_address(np.zeros((8, 8, 3), dtype=np.uint8), subject=subject)
    response["scale"] = {
        "address": addr["embed"],
        "gate": addr["gate"],
        "field": addr["field"],
        "core_step": step_shared(),
        "search": search_shared(),
        "phasor": phasor_shared(),
        "shared_core": shared["core"] is not None,
        "shared_field": shared["field"] is not None,
    }
    return response
