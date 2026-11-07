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

from typing import Any, Optional

import numpy as np

from resileos.ui.framework_gate import gate_candidate
from resileos.ui.residual_embed import address_triple, embed_frame

try:
    from resileos.substrate.oscillator import KuramotoField
    _HAS_KURAMOTO = True
except ImportError:
    KuramotoField = None
    _HAS_KURAMOTO = False


def persona_phase(persona: str) -> float:
    """Stable phase offset from a persona name. Cheap tint."""
    if not persona:
        return 0.0
    return (sum(ord(c) for c in persona) % 360) * np.pi / 180.0


def scale_address(
    arr: Optional[np.ndarray] = None,
    *,
    belt: int = 0,
    frame: int = 0,
    persona: str = "",
    subject: str = "state",
    stored: Optional[list[dict[str, str]]] = None,
    eat_accepted: bool = False,
) -> dict[str, Any]:
    """One address for a frame, a fact, or a world state.

    Returns the embed, the field phases, the gated triple, and the frame label.
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
    if _HAS_KURAMOTO and KuramotoField is not None:
        field = KuramotoField(n=3)
        field.theta = np.array(theta)
        if hasattr(field, "step"):
            field.step()
        theta = [float(x) for x in field.theta]
        backend = "kuramoto"
    triple = address_triple(embed, subject=subject)
    gated = gate_candidate(triple, stored=stored or [], eat_accepted=eat_accepted)
    return {
        "embed": embed,
        "persona": persona,
        "field": {"backend": backend, "theta": [round(t, 4) for t in theta]},
        "triple": triple,
        "gate": gated,
        "scale": "belt/frame/residual",
    }
