"""Wire UI perception into the kin. Image, audio, video, language, and art all
write into Psyche, then Athena judges, then Apollo can hop on the resulting
rows.

Two paths:

    wire_perception(psyche, perceived, learn_fn=titan.learn)
        SEPARATED. Athena proposes, verifiers + council review, Zeus
        applies only if every reviewer approves. Claims are captured by
        a shim; the real learn function is called only in apply().

    wire_perception(psyche, perceived, eat_fn=some_fn)
        LEGACY. judge() calls eat_fn directly. No separation — the writer
        and the applier are the same call. Emits a DeprecationWarning.

Prefer learn_fn. eat_fn is kept for compatibility with existing call
sites and tests.
"""
from __future__ import annotations

import warnings
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
    learn_fn: Optional[Callable[[str, str, str], None]] = None,
    ask_fn: Optional[Callable[[str, str], Any]] = None,
    use_council: bool = True,
    profile: str = "personal",
) -> dict[str, Any]:
    """One call from any UI perceive module into the kin.

    If `learn_fn` is provided, the perception runs through the separated
    cycle (write → review → apply) and returns harness fields.
    If only `eat_fn` is provided, falls back to the legacy direct write
    and warns that the cycle is unverified.
    """
    if learn_fn is not None:
        from resileos.kin.perception_kin import perception_cycle

        result = perception_cycle(
            psyche,
            perceived,
            learn_fn=learn_fn,
            ask_fn=ask_fn,
            others=others,
            use_council=use_council,
            profile=profile,
        )
        # Normalise to the legacy shape so existing callers keep working,
        # plus the new harness fields.
        return {
            # Legacy keys (were always present)
            "state": result.get("psyche_state", dict(psyche.state)),
            "rows": result.get("hub_rows", psyche.hub_rows()),
            "judgment": {
                "ok": bool(result.get("applied", False)),
                "reading": result.get("verdict", "")
                if isinstance(result.get("verdict"), str)
                else "",
                "gate": {
                    "frame": "applied" if result.get("applied") else "abstained"
                },
                "applied": bool(result.get("applied", False)),
            },
            # New keys for callers who want them
            "applied": bool(result.get("applied", False)),
            "learned": int(result.get("learned", 0) or 0),
            "verification": result.get("verification", {}),
            "verdicts": result.get("verdicts", []),
        }

    # Legacy path: write-and-approve in one call.
    warnings.warn(
        "wire_perception(eat_fn=...) writes facts without review. "
        "Pass learn_fn=<titan.learn> instead to route through the "
        "separated cycle (write -> review -> apply).",
        DeprecationWarning,
        stacklevel=2,
    )
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


__all__ = ["wire_perception"]
