"""Wire UI perception into the kin.

Image, audio, video, language, and art all write into Psyche,
then Athena judges, then Apollo can hop on the resulting rows.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.kin.athena import judge
from resileos.kin.perceive_into import perceive_into
from resileos.kin.psyche import Psyche


def wire_perception(
    psyche: Psyche,
    perceived: dict[str, Any],
    *,
    others: Optional[list[dict[str, Any]]] = None,
    eat_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """One call from any UI perceive module into the kin."""
    perceive_into(psyche, perceived)
    percs = [perceived] + (others or [])
    reading = judge(
        percs,
        subject=psyche.subject,
        eat_fn=eat_fn,
        frames=psyche.state.get("frames"),
        drives=psyche.state.get("drives"),
    )
    return {
        "state": psyche.state,
        "rows": psyche.hub_rows(),
        "judgment": reading,
    }
