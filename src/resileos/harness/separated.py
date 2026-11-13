"""Separated cycle: write / review / apply (SpaceXAI Separation pattern).

Writers produce a Proposal. Reviewers produce a Verdict. The head (Zeus)
applies only if every reviewer approves.

Real reviewers wired:
    run_verifiers  (verifiers.py)  — 9-checker deterministic swarm
    council_query  (council.py)    — hub arbitration, CONFLICT detection
    judge          (athena.py)     — optional frame gate

Writers receive a _capture_eat shim, not the real learn. Claims queue on
the proposal; only apply() calls the real learn function, after review.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    apollo_success,
    budget_and_stuck_guard,
    evidence_attach,
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
    """eat_fn shim that queues claims instead of learning them."""
    def eat(claim: Any) -> dict:
        s = r = o = None
        if isinstance(claim, str):
            parts = claim.split()
            if len(parts) >= 3:
                s, r, o = parts[0], parts[1], " ".join(parts[2:])
        elif isinstance(claim, dict):
            s = claim.get("subject")
            r = claim.get("relation")
            o = claim.get("obj") or claim.get("object")
        if s and r and o is not None and str(o) != "":
            claims.append((str(s), str(r), str(o)))
        return {"accepted": True, "captured": True, "learning": False}
    return eat


class SeparatedCycle:
    def __init__(self, *, id_prefix: str = "sep") -> None:
        self.id_prefix = id_prefix

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
            rows = result.get("hub_rows") or result.get("rows")
            if isinstance(rows, list):
                hub_rows = [r for r in rows if isinstance(r, dict)]
                for row in hub_rows:
                    s, r_, o = row.get("subject"), row.get("relation"), row.get("obj")
                    if s and r_ and o is not None and str(o) != "":
                        claims.append((str(s), str(r_), str(o)))

        return Proposal(
            id=packet.id,
            writer=writer,
            action_type=action_type or writer,
            result=result,
            claims=claims,
            hub_rows=hub_rows,
            packet=packet,
        )

    # ── reviewer 1: deterministic verifier swarm ─────────────────
    def review_verifiers(
        self,
        proposal: Proposal,
        *,
        ctx: Optional[dict] = None,
    ) -> Verdict:
        from resileos.kin.verifiers import run_verifiers

        if not proposal.claims:
            return Verdict(
                proposal.id, "verifiers", False,
                "no claims to verify",
                evidence=[{"matched": 0}],
            )

        ctx = dict(ctx or {})
        rejected: list[dict] = []
        accepted = 0
        trail_all: list[dict] = []

        # Optional validity windows aligned with proposal.claims. Eat's
        # temporal envelope sets these so the verifier swarm checks the
        # same interval Titanos will store.
        bounds = proposal.metadata.get("temporal_bounds") or []
        for index, (s, r, o) in enumerate(proposal.claims):
            row: dict[str, Any] = {"subject": s, "relation": r, "obj": o}
            if index < len(bounds) and isinstance(bounds[index], (list, tuple)):
                valid_from, valid_to = (list(bounds[index]) + [None, None])[:2]
                if valid_from:
                    row["valid_from"] = str(valid_from)
                if valid_to:
                    row["valid_to"] = str(valid_to)
            rep = run_verifiers(row, ctx=ctx)
            trail_all.append({
                "claim": f"{s} {r} {o}",
                "action": rep.action,
                "reason": rep.reason,
                "frame": rep.frame,
            })
            if rep.action == "accept":
                accepted += 1
            elif rep.action == "reject":
                rejected.append({"claim": f"{s} {r} {o}", "reason": rep.reason})
            # abstain → neither accepted nor hard-rejected; treated as reject
            elif rep.action == "abstain":
                rejected.append({"claim": f"{s} {r} {o}", "reason": "abstained"})

        evidence = [{
            "matched": len(proposal.claims),
            "accepted": accepted,
            "rejected": len(rejected),
            "trail": trail_all,
        }]

        if rejected:
            return Verdict(
                proposal.id, "verifiers", False,
                f"{len(rejected)} claim(s) rejected: {rejected[0]['reason']}",
                evidence=evidence,
            )
        if accepted == 0:
            return Verdict(
                proposal.id, "verifiers", False,
                "zero claims accepted", evidence=evidence,
            )
        return Verdict(
            proposal.id, "verifiers", True,
            f"{accepted}/{len(proposal.claims)} claims accepted",
            evidence=evidence,
        )

    # ── reviewer 2: council hub arbitration ──────────────────────
    def review_council(
        self,
        proposal: Proposal,
        *,
        ask_fn: Callable[[str, str], Any],
        profile: str = "personal",
    ) -> Verdict:
        from resileos.kin.council import council_query

        if not callable(ask_fn):
            return Verdict(
                proposal.id, "council", True,
                "no ask_fn; council skipped",
                evidence=[{"matched": len(proposal.claims), "skipped": True}],
            )

        conflicts: list[dict] = []
        for s, r, _o in proposal.claims:
            try:
                res = council_query(s, r, ask_fn, profile=profile)
            except Exception as e:
                conflicts.append({"claim": f"{s} {r}", "error": str(e)})
                continue
            if res.status == "CONFLICT":
                conflicts.append({
                    "claim": f"{s} {r}",
                    "conflicts": list(res.conflicts),
                    "winner_hub": res.winner_hub,
                })

        evidence = [{
            "matched": len(proposal.claims),
            "conflicts": len(conflicts),
            "conflict_detail": conflicts,
        }]

        if conflicts:
            return Verdict(
                proposal.id, "council", False,
                f"{len(conflicts)} hub conflict(s)",
                evidence=evidence,
            )
        return Verdict(
            proposal.id, "council", True,
            "no hub conflicts", evidence=evidence,
        )

    # ── reviewer 3 (optional): Athena frame gate ─────────────────
    def review_athena(
        self,
        proposal: Proposal,
        *,
        subject: str = "world:reading",
        frames: Optional[list[dict]] = None,
        drives: Optional[dict[str, float]] = None,
    ) -> Verdict:
        from resileos.kin.athena import judge

        perceptions = [
            {"subject": s, "address": {"residual_bin": "review"}}
            for s, _r, _o in proposal.claims[:5]
        ]
        try:
            out = judge(
                perceptions,
                subject=subject,
                eat_fn=None,
                frames=frames,
                drives=drives,
            )
        except Exception as e:
            return Verdict(
                proposal.id, "athena", False,
                f"athena failed: {e}", evidence=[{"matched": 0}],
            )

        frame = (out.get("gate") or {}).get("frame", "")
        approved = bool(out.get("ok")) and frame not in ("abstained", "unresolved")
        return Verdict(
            proposal.id, "athena", approved,
            f"frame={frame}",
            evidence=[{
                "matched": len(proposal.claims),
                "frame": frame,
                "reading": out.get("reading", "")[:120],
            }],
        )

    # ── apply ────────────────────────────────────────────────────
    def apply(
        self,
        proposal: Proposal,
        verdict: Verdict,
        learn_fn: Callable[[str, str, str], None],
    ) -> dict:
        if proposal.metadata.get("guard_fail"):
            return {"applied": False, "reason": "guard_fail"}
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
        # Persist reviewer evidence onto the packet before verification.
        if proposal.packet is not None and verdict.evidence:
            for e in verdict.evidence:
                evidence_attach(e, verdict.reviewer, proposal.packet.to_dict())

        apollo = apollo_success(
            proposal.result if isinstance(proposal.result, dict) else {}
        )
        v = verify_on_stop(
            (proposal.packet.to_dict()
             if proposal.packet is not None else packet_dict),
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
    reviewers: list[tuple[str, Callable[[Proposal], Verdict]]],
    learn_fn: Callable[[str, str, str], None],
    *,
    cycle: Optional[SeparatedCycle] = None,
) -> dict:
    """Zeus: no write, no approve. Apply only if every reviewer approves."""
    sc = cycle or SeparatedCycle()
    verdicts: list[Verdict] = []
    for name, fn in reviewers:
        raw = fn(proposal)
        if isinstance(raw, tuple):
            approved = bool(raw[0]) if raw else False
            reason = str(raw[1]) if len(raw) > 1 else ""
            evidence = list(raw[2]) if len(raw) > 2 and raw[2] else []
            v = Verdict(proposal.id, name, approved, reason, evidence)
        elif isinstance(raw, Verdict):
            v = raw
        else:
            v = Verdict(
                proposal.id,
                name,
                bool(getattr(raw, "approved", False)),
                str(getattr(raw, "reason", "")),
                list(getattr(raw, "evidence", []) or []),
            )
        verdicts.append(v)
        if not v.approved:
            return {
                "applied": False,
                "reason": f"reviewer {name} rejected: {v.reason}",
                "verdicts": [x.__dict__ for x in verdicts],
                "verification": {"verified": False, "reason": v.reason},
            }
    result = sc.apply(proposal, verdicts[-1], learn_fn)
    result["verdicts"] = [x.__dict__ for x in verdicts]
    return result


def run_separated(
    writer_fn: Callable[..., Any],
    *,
    writer_name: str,
    action_type: str,
    learn_fn: Callable[[str, str, str], None],
    ask_fn: Optional[Callable[[str, str], Any]] = None,
    use_council: bool = True,
    use_athena: bool = False,
    profile: str = "personal",
    verifier_ctx: Optional[dict] = None,
    writer_args: tuple = (),
    writer_kwargs: Optional[dict] = None,
) -> dict:
    """One-call separated cycle with the real reviewers wired."""
    sc = SeparatedCycle()
    proposal = sc.propose(
        writer_name, writer_fn, *writer_args,
        action_type=action_type,
        **(writer_kwargs or {}),
    )
    reviewers = default_reviewers(
        sc,
        ask_fn=ask_fn,
        use_council=use_council,
        use_athena=use_athena,
        profile=profile,
        verifier_ctx=verifier_ctx,
    )
    return zeus_head(proposal, reviewers, learn_fn, cycle=sc)


def default_reviewers(
    sc: SeparatedCycle,
    *,
    ask_fn: Optional[Callable[[str, str], Any]] = None,
    use_council: bool = True,
    use_athena: bool = False,
    profile: str = "personal",
    verifier_ctx: Optional[dict] = None,
) -> list[tuple[str, Callable[[Proposal], Verdict]]]:
    """The reviewer set ``run_separated`` assigns.

    The verifier swarm always reviews. The council reviews when an
    ``ask_fn`` is supplied and ``use_council`` is on. Athena reviews only
    when asked. Other callers reuse this list so the set stays in one place.
    """
    reviewers: list[tuple[str, Callable[[Proposal], Verdict]]] = [
        ("verifiers", lambda p: sc.review_verifiers(p, ctx=verifier_ctx)),
    ]
    if use_council and ask_fn is not None:
        reviewers.append(
            ("council", lambda p: sc.review_council(
                p, ask_fn=ask_fn, profile=profile
            ))
        )
    if use_athena:
        reviewers.append(("athena", lambda p: sc.review_athena(p)))
    return reviewers


def _claims_from_artefact(artefact: Any) -> list[tuple[str, str, str]]:
    """Triples the maker returned. Zeus learns these only after approval."""
    claims: list[tuple[str, str, str]] = []
    if not isinstance(artefact, dict):
        return claims
    raw: list[Any] = []
    if isinstance(artefact.get("claims"), list):
        raw.extend(artefact["claims"])
    rows = artefact.get("hub_rows") or artefact.get("rows")
    if isinstance(rows, list):
        raw.extend(rows)
    for item in raw:
        subject = relation = obj = None
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            subject, relation, obj = item[0], item[1], item[2]
        elif isinstance(item, dict):
            subject = item.get("subject")
            relation = item.get("relation")
            obj = item.get("obj")
            if obj is None:
                obj = item.get("object")
        if subject and relation and obj is not None and str(obj) != "":
            claims.append((str(subject), str(relation), str(obj)))
    return claims


def _noop_learn(_subject: str, _relation: str, _obj: str) -> None:
    return None


def maker_blind_verifier_cycle(
    task: str,
    maker_fn: Callable[..., Any],
    residual_packet: Any = None,
    hades: Any = None,
    *,
    spec: Any = None,
    learn_fn: Callable[[str, str, str], None] | None = None,
    supplement_fn: Callable[[dict[str, Any]], Any] | None = None,
    max_rounds: int = 1,
) -> dict[str, Any]:
    """Maker produces an artefact. Momus reviews it blind. Zeus learns.

    Shared durable state is the residual hash and, when the maker packet
    is verified, the Hades lesson. ``control.verified is False`` skips
    the checkpoint and leaves the lesson unset. Momus receives the
    artefact, the spec (or the task text), and the residual hash. It does
    not receive control history or author notes.

    A ``need_more`` result is not approval. The cycle may ask the maker,
    once, for only the listed fields. ``max_rounds`` cannot exceed
    ``MAX_NEED_MORE_ROUNDS``. ``learn_fn`` runs only when the final Momus
    outcome is ``approved`` and Zeus applies that verdict.
    """
    from resileos.kin.demigods.checks import (
        MAX_NEED_MORE_ROUNDS,
        OUTCOME_APPROVED,
        apply_blind_supplement,
        momus_review,
    )
    from resileos.kin.demigods.hierarchy import DemigodError, durable_cross_attempt
    from resileos.kin.demigods.router import demigod_dismiss, demigod_summon

    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool):
        raise DemigodError(
            f"need_more rounds are capped at {MAX_NEED_MORE_ROUNDS}"
        )
    if max_rounds < 0 or max_rounds > MAX_NEED_MORE_ROUNDS:
        raise DemigodError(
            f"need_more rounds are capped at {MAX_NEED_MORE_ROUNDS}"
        )

    control = ControlPacket(id="maker")
    artefact = maker_fn(task, control)

    residual_hash = None
    if residual_packet is not None:
        residual_hash = getattr(residual_packet, "packet_hash", None)
        if residual_hash is None and isinstance(residual_packet, dict):
            residual_hash = residual_packet.get("packet_hash")

    lesson = None
    lesson_skipped = None
    if hades is not None and control.verified:
        checkpoint = hades.save(control, residual_packet_hash=residual_hash)
        lesson = checkpoint.lesson
    elif not control.verified:
        lesson_skipped = "control.verified is false"
    else:
        lesson_skipped = "no hades store"

    review_spec = task if spec is None else spec
    review_packet = ControlPacket(id="reviewer")
    review_packet.append(
        {
            "event": "blind_review",
            "artefact_chars": len(str(artefact)),
            "residual_hash": residual_hash,
            "lesson": lesson,
        }
    )
    summoned = demigod_summon("momus", review_packet)
    rounds = 0
    try:
        result = momus_review(artefact, review_spec, residual_hash)
        while (
            result.outcome == "need_more"
            and rounds < max_rounds
            and supplement_fn is not None
        ):
            # The request is the code list only. No packet history.
            request = {
                "round": rounds + 1,
                "need_more": [item.to_dict() for item in result.need_more],
            }
            supplied = supplement_fn(request)
            artefact, review_spec, residual_hash = apply_blind_supplement(
                artefact,
                review_spec,
                residual_hash,
                result.need_more,
                supplied,
            )
            rounds += 1
            result = momus_review(artefact, review_spec, residual_hash)

        approved = (
            result.outcome == OUTCOME_APPROVED
            and bool(result.verified)
            and not result.need_more
        )

        def _review(proposal: Proposal) -> Verdict:
            return Verdict(
                proposal.id,
                "momus",
                approved,
                result.reason,
                evidence=list(result.evidence),
            )

        proposal = Proposal(
            id=control.id,
            writer="maker",
            action_type="maker_blind",
            result=artefact if isinstance(artefact, dict) else {"artefact": artefact},
            claims=_claims_from_artefact(artefact),
            packet=control,
        )
        head = zeus_head(
            proposal,
            [("momus", _review)],
            learn_fn or _noop_learn,
        )
    finally:
        demigod_dismiss("momus", review_packet)

    findings = result.to_dict()
    durable = durable_cross_attempt(
        {"lesson": lesson, "residual_packet_hash": residual_hash}
    )
    return {
        "artefact": artefact,
        "lesson": lesson,
        "lesson_skipped": lesson_skipped,
        "residual_hash": residual_hash,
        "findings": findings,
        "outcome": result.outcome,
        "need_more": [item.to_dict() for item in result.need_more],
        "need_more_rounds": rounds,
        "durable": durable,
        "guide_chars": int(summoned.get("body_chars") or 0),
        "review_guides": list(review_packet.guides_loaded),
        "head": head,
        "hierarchy": (
            "maker served; Momus served under Hermes; residual core final"
        ),
    }


__all__ = [
    "Proposal", "Verdict", "SeparatedCycle", "zeus_head",
    "run_separated", "default_reviewers", "maker_blind_verifier_cycle", "_capture_eat",
]
