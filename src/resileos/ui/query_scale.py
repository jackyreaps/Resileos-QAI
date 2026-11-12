"""Attach scale, core step, search, and phasor to a query response."""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address
from resileos.ui.shared_state import get_shared, phasor_shared, search_shared, step_shared


def to_jsonable(obj: Any) -> Any:
    """Replace ndarrays and numpy scalars so FastAPI can encode the body."""
    if isinstance(obj, dict):
        return {str(to_jsonable(k)): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, np.generic):
        if isinstance(obj, np.complexfloating):
            return {"re": float(obj.real), "im": float(obj.imag)}
        return to_jsonable(obj.item())
    if isinstance(obj, complex):
        return {"re": float(obj.real), "im": float(obj.imag)}
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    return obj


def with_scale(response: dict[str, Any], subject: str, relation: str) -> dict[str, Any]:
    shared = get_shared()
    addr = scale_address(
        np.zeros((8, 8, 3), dtype=np.uint8),
        subject=subject,
        step_core=False,
    )
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
    return to_jsonable(response)
