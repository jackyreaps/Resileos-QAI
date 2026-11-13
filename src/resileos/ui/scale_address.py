"""Scale address: one coordinate for frame, fact, and world state.

Ties existing pieces:
  - residual embed (belt / frame / residual bin)
  - Kuramoto field (when present)
  - eat gate decision
  - persona tint

Scaffold for sub-quantum to cosmos. The residual bin is still a
placeholder until the suite residual is coded. The shape is stable.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.core_bridge import core_step_from_address, search_from_field
from resileos.ui.framework_gate import gate_candidate
from resileos.ui.residual_embed import address_triple, embed_frame


def _kuramoto_field():
    """Import after package init. A module-level import is circular."""
    try:
        from resileos.substrate.oscillator import KuramotoField
    except ImportError:
        return None
    return KuramotoField


def persona_phase(persona: str) -> float:
    """Stable phase offset from a persona name. Cheap tint."""
    if not persona:
        return 0.0
    return (sum(ord(c) for c in persona) % 360) * np.pi / 180.0


def scale_address(
    arr: np.ndarray | None = None,
    *,
    belt: int = 0,
    frame: int = 0,
    persona: str = "",
    subject: str = "state",
    stored: list[dict[str, str]] | None = None,
    eat_accepted: bool = False,
    step_core: bool = True,
) -> dict[str, Any]:
    """One address for a frame, a fact, or a world state.

    Returns the embed, the field phases, the gated triple, and the frame label.
    ``step_core=False`` skips ``ResidualCore.step``. Studio and other visual
    callers use that so a scale address does not update a scar matrix.
    """
    if arr is None:
        arr = np.zeros((8, 8, 3), dtype=np.uint8)
    embed = embed_frame(arr, belt=belt, frame=frame)
    phase = persona_phase(persona)
    theta = [
        embed["mean_luma"] * np.pi + phase,
        embed["edge_density"] * np.pi,
        (belt % 3) * 0.5,
    ]
    backend = "fallback"
    KuramotoField = _kuramoto_field()
    if KuramotoField is not None:
        field = KuramotoField(3)
        field.theta = np.asarray(theta, dtype=float)
        field.step(epsilon=1.0)
        theta = [float(x) for x in field.theta]
        backend = "kuramoto"
    triple = address_triple(embed, subject=subject)
    gated = gate_candidate(triple, stored=stored or [], eat_accepted=eat_accepted)
    field_info = {"backend": backend, "theta": [round(t, 4) for t in theta]}
    if step_core:
        core = core_step_from_address(embed)
    else:
        core = {
            "backend": "not_stepped",
            "packet_hash": None,
            "layers": 0,
            "scar_matrix_updated": False,
            "learned": False,
        }
    search = search_from_field(field_info["theta"])
    return {
        "embed": embed,
        "persona": persona,
        "field": field_info,
        "core": core,
        "search": search,
        "triple": triple,
        "gate": gated,
        "scale": "belt/frame/residual",
    }
