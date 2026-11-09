"""Separated cycle: write / review / apply (SpaceXAI Separation pattern).

The bot that writes is never the bot that approves. A writer produces a
Proposal; a reviewer produces a Verdict; the head (Zeus) applies only if
the verdict is approved.

This sits *above* KinBundle.cycle. It does not replace it. The existing
cycle stays for in-process use; SeparatedCycle wraps it and the new kin
(Apollo, Psyche, Athena, Metis) so harness state and evidence travel with
every proposal.

Key property: writers receive a `_capture_eat` shim, not the real
`titan.learn`. Their `eat_fn` calls append claims to the proposal instead
of learning them. Only `apply()` calls the real learn function, and only
after review.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    apollo_success,
    budget_and_stuck_guard,
    evidence_attach_raw,
    guide_load,
    verification_required,
    verify_on_stop,
)

_GUIDES = ["docs/harness/CONSTRAINTS.md", "docs/harness/AGENTS.md"]


@dataclass
class Proposal:
    id: str
    writer: str
    action_type: str
    result: Any
    claims: list[tuple[str, str, str]] = field(default_factory=list)
    hub_rows: list[dict[str, str]] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    packet: Optional[ControlPacket] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Verdict:
    proposal_id: str
    reviewer: str
    approved: bool
    reason: str
    evidence: list[dict] = field(default_factory=list)


def _capture_eat(claims: list[tuple[str, str, str]]):
    """Return an eat_fn that appends claims instead of learning them.

    Accepts the three shapes the kin use: a whitespace-separated string,
    a dict with subject/relation/obj, or a dict with an `object` key.
    """
    def eat(claim: Any) -> dict:
        s = r = o = None
        if isinstance(claim, str):
            parts = claim.split()
            if len(parts) == 3:
                s, r, o = parts
        elif isinstance(claim, dict):
            s = claim.get("subject")
            r = claim.get("relation")
            o = claim.get("obj") or claim.get("object")
        if s and r and o:
            claims.append((str(s), str(r), str(o)))
        return {"accepted": True, "captured": True, "learning": False}
    return eat


class SeparatedCycle:
    def __init__(self, *, id_prefix: str = "sep") -> None:
        self.id_prefix = id_prefix

    # ── write ────────────────────────────────────────────────────
    def propose(
        self,
        writer: str,
        writer_fn: Callable[..., Any],
        *args: Any,
        action_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Proposal:
        packet = ControlPacket(
            id=f"{self.id_prefix}-{writer}-{uuid.uuid4().hex[:8]}"
        )
        guide_load(_GUIDES, packet.to_dict())

        guard = budget_and_stuck_guard(packet.to_dict())
        if not guard["ok"]:
            return Proposal(
                id=packet.id,
                writer=writer,
                action_type=action_type or writer,
                result={"error": "guard_fail", "reason": guard["reason"]},
                packet=packet,
                metadata={"guard_fail": True},
            )

        claims: list[tuple[str, str, str]] = []
        kwargs.setdefault("eat_fn", _capture_eat(claims))
        result = writer_fn(*args, **kwargs)

        hub_rows: list[dict[str, str]] = []
        if isinstance(result, dict):
            rows = result.get("hub_rows")
            if isinstance(rows, list):
                hub_rows = [r for r in rows if isinstance(r, dict)]

        return Proposal(
            id=packet.id,
            writer=writer,
            action_type=action_type or writer,
            result=result,
            claims=claims,
            hub_rows=hub_rows,
            packet=packet,
        )

    # ── review ───────────────────────────────────────────────────
    def review(
        self,
        proposal: Proposal,
        reviewer: str,
        reviewer_fn: Callable[[Proposal], tuple[bool, str, list[dict]]],
    ) -> Verdict:
        approved, reason, evidence = reviewer_fn(proposal)
        if proposal.packet is not None and evidence:
            for e in evidence:
                try:
                    evidence_attach_raw(
                        e, reviewer, proposal.packet.to_dict()
                    )
                except (ValueError, TypeError):
                    pass
        return Verdict(
            proposal_id=proposal.id,
            reviewer=reviewer,
            approved=approved,
            reason=reason,
            evidence=evidence,
        )

    # ── apply ────────────────────────────────────────────────────
    def apply(
        self,
        proposal: Proposal,
        verdict: Verdict,
        learn_fn: Callable[[str, str, str], None],
    ) -> dict:
        if not verdict.approved:
            return {"applied": False, "reason": verdict.reason}

        learned = 0
        for s, r, o in proposal.claims:
            try:
                learn_fn(s, r, o)
                learned += 1
            except Exception:
                pass

        verification = verification_required(proposal.action_type)
        packet_dict = (
            proposal.packet.to_dict()
            if proposal.packet is not None
            else {"verified": False, "scars": [], "evidence": []}
        )
        apollo = apollo_success(
            proposal.result if isinstance(proposal.result, dict) else {}
        )
        v = verify_on_stop(
            packet_dict,
            apollo,
            require_evidence=verification["requires_verification"],
        )
        return {
            "applied": True,
            "learned": learned,
            "hub_rows": len(proposal.hub_rows),
            "verification": v,
            "verdict": verdict.reason,
        }


def zeus_head(
    proposal: Proposal,
    reviewers: list[
        tuple[str, Callable[[Proposal], tuple[bool, str, list[dict]]]]
    ],
    learn_fn: Callable[[str, str, str], None],
    *,
    cycle: Optional[SeparatedCycle] = None,
) -> dict:
    """Zeus as head: no write, no approve, only apply if all reviewers pass.

    Order matters. The first reviewer that rejects stops the apply.
    """
    sc = cycle or SeparatedCycle()
    verdicts: list[Verdict] = []
    for name, fn in reviewers:
        v = sc.review(proposal, name, fn)
        verdicts.append(v)
        if not v.approved:
            return {
                "applied": False,
                "reason": f"reviewer {name} rejected: {v.reason}",
                "verdicts": [x.__dict__ for x in verdicts],
            }
    result = sc.apply(proposal, verdicts[-1], learn_fn)
    result["verdicts"] = [x.__dict__ for x in verdicts]
    return result


__all__ = [
    "Proposal",
    "Verdict",
    "SeparatedCycle",
    "zeus_head",
    "_capture_eat",
]
