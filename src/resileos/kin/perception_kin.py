"""Perception kin: perceived input through the separated cycle.

wire_perception on main calls judge(eat_fn=real_eat) directly. That is
write-and-approve in one body — the pattern the Separation invariant
forbids. This module routes the same pipeline through the separated
cycle: Psyche observes, Athena proposes a judgment, verifiers + council
review, Zeus applies.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.harness.separated import SeparatedCycle, zeus_head
from resileos.kin.athena import judge
from resileos.kin.perceive_into import perceive_into
from resileos.kin.psyche import Psyche


def perception_cycle(
    psyche: Psyche,
    perceived: dict[str, Any],
    *,
    learn_fn: Callable[[str, str, str], None],
    ask_fn: Optional[Callable[[str, str], Any]] = None,
    others: Optional[list[dict[str, Any]]] = None,
    use_council: bool = True,
    profile: str = "personal",
) -> dict:
    """Perceive -> propose -> review -> apply. Zeus applies only if passed."""
    # 1. Observation writes into Psyche (no store write, state only)
    perceive_into(psyche, perceived)

    # 2. Writer: Athena judges the current perception set, capturing claims
    percs = [perceived] + (others or [])
    sc = SeparatedCycle(id_prefix="perceive")
    proposal = sc.propose(
        "athena",
        judge,
        percs,
        subject=psyche.subject,
        frames=psyche.state.get("frames"),
        drives=psyche.state.get("drives"),
        action_type="athena_judge",
    )

    # 3. Reviewers: verifier swarm + council + athena frame gate
    reviewers = [
        ("verifiers", lambda p: sc.review_verifiers(p)),
    ]
    if use_council and ask_fn is not None:
        reviewers.append(
            ("council", lambda p: sc.review_council(
                p, ask_fn=ask_fn, profile=profile
            ))
        )
    reviewers.append(("athena", lambda p: sc.review_athena(p, subject=psyche.subject)))

    # 4. Head: apply only if all reviewers approve
    result = zeus_head(proposal, reviewers, learn_fn, cycle=sc)
    result["psyche_state"] = dict(psyche.state)
    result["hub_rows"] = psyche.hub_rows()
    return result


__all__ = ["perception_cycle"]
