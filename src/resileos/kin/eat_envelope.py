"""Eat envelope: untrusted candidates -> Eat -> Zeus reviewers -> Titanos.

An outer-layer producer (for example the Hermes search legion) hands Eat a
*candidate envelope*. An envelope is untrusted. This module is the only
path from an envelope to a Titanos write, and it runs in this order:

1. ``check_envelope``: strip attention metrics, require a structured
   triple, parse the validity window, abstain on bad bounds.
2. ``eat_filter``: the existing Eat filter and verifier swarm.
3. Interval conflict: a claim whose half-open window ``[valid_from,
   valid_to)`` overlaps a stored, explicitly bounded fact with a
   different object for the same subject and relation is CONFLICT. Two
   claims in one batch that overlap that way are both CONFLICT. Neither
   side is written. The result does not depend on batch order.
4. Zeus head: the claims that survived go through ``zeus_head`` with the
   reviewer set from ``default_reviewers`` (the same set
   ``run_separated`` uses). Titanos is written only if every assigned
   reviewer approves.

Attention, ranking, and buzz metrics (likes, shares, views, rank, and so
on) are removed before Eat sees the envelope. They are never stored. The
stripped key names are reported; the values are not.

Prose never becomes a fact here. A string claim abstains as
``unstructured_prose`` without being parsed, because web text such as
"Paris is the capital" would otherwise parse as a triple.

Studio, visual, and persona paths do not call this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Optional

from resileos.kin.eat import EatDecision, eat_filter
from resileos.kin.verifiers import _parse_iso

ENVELOPE_VERSION = "eat-envelope/1"

# Attention / ranking / buzz signals. Popularity is not evidence, so these
# are dropped before Eat and never reach Titanos.
ATTENTION_KEYS = frozenset(
    {
        "attention",
        "buzz",
        "clicks",
        "comments_count",
        "engagement",
        "favorites",
        "followers",
        "hotness",
        "impressions",
        "likes",
        "popularity",
        "position",
        "rank",
        "ranking",
        "reactions",
        "relevance",
        "reposts",
        "retweets",
        "score",
        "shares",
        "trending",
        "upvotes",
        "views",
        "virality",
        "votes",
    }
)

_CLAIM_KEYS = ("subject", "relation", "obj", "object", "source", "hub")


@dataclass
class EnvelopeCheck:
    """Outcome of one envelope. ``action`` is accept | reject | abstain | conflict."""

    action: str
    reason: str = ""
    subject: str = ""
    relation: str = ""
    obj: str = ""
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    source: str = ""
    stripped: list[str] = field(default_factory=list)
    eat: Optional[dict[str, Any]] = None
    conflicts_with: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def key(self) -> tuple[str, str, str]:
        return (self.subject, self.relation, self.obj)


def strip_attention(payload: Any) -> tuple[Any, list[str]]:
    """Drop attention keys at any depth. Returns (clean, sorted key names)."""
    removed: set[str] = set()

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if str(key).strip().lower() in ATTENTION_KEYS:
                    removed.add(str(key).strip().lower())
                    continue
                out[key] = walk(item)
            return out
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return walk(payload), sorted(removed)


def _bound(raw: Any) -> tuple[Optional[str], Optional[datetime], bool]:
    """(text, parsed, ok). Empty means unbounded and is ok."""
    if raw is None:
        return None, None, True
    text = str(raw).strip()
    if not text:
        return None, None, True
    parsed = _parse_iso(text)
    if parsed is None:
        return text, None, False
    return text, parsed, True


def check_envelope(
    envelope: Any,
    *,
    eat_kw: Optional[dict[str, Any]] = None,
) -> EnvelopeCheck:
    """Validate one candidate envelope and run it through ``eat_filter``.

    The envelope is ``{"claim": {...}, "source": ..., ...}`` or a bare claim
    dict. Validity may be given as ``valid_from`` and ``valid_to`` (or the
    older ``valid_until``) on the claim or on the envelope.
    """
    clean, stripped = strip_attention(envelope if envelope is not None else {})
    if isinstance(clean, dict) and "claim" in clean:
        claim = clean.get("claim")
        outer = clean
    else:
        claim = clean
        outer = clean if isinstance(clean, dict) else {}
    if not isinstance(claim, dict):
        return EnvelopeCheck(
            action="abstain",
            reason="unstructured_prose",
            stripped=stripped,
            source=str(outer.get("source") or "") if isinstance(outer, dict) else "",
        )

    def pick(name: str) -> Any:
        if claim.get(name) not in (None, ""):
            return claim.get(name)
        return outer.get(name) if isinstance(outer, dict) else None

    vf_text, vf, vf_ok = _bound(pick("valid_from"))
    raw_to = pick("valid_to")
    if raw_to in (None, ""):
        raw_to = pick("valid_until")
    vt_text, vt, vt_ok = _bound(raw_to)
    source = str(pick("source") or "")
    base = {
        "subject": str(claim.get("subject") or "").strip(),
        "relation": str(claim.get("relation") or "").strip(),
        "obj": str(
            claim.get("obj") if claim.get("obj") is not None else claim.get("object") or ""
        ).strip(),
    }
    if not vf_ok:
        return EnvelopeCheck(action="abstain", reason="invalid_valid_from", source=source, stripped=stripped, **base)
    if not vt_ok:
        return EnvelopeCheck(action="abstain", reason="invalid_valid_to", source=source, stripped=stripped, **base)
    if vf is not None and vt is not None and not vf < vt:
        # Half-open [from, to) needs from < to. An empty or inverted window
        # is not a fact Eat can place in time.
        return EnvelopeCheck(
            action="abstain",
            reason="empty_or_inverted_interval",
            valid_from=vf_text,
            valid_to=vt_text,
            source=source,
            stripped=stripped,
            **base,
        )

    row = {key: claim[key] for key in _CLAIM_KEYS if key in claim}
    if source:
        row["source"] = source
    if vf_text:
        row["valid_from"] = vf_text
    if vt_text:
        row["valid_to"] = vt_text
    decision: EatDecision = eat_filter(row, **dict(eat_kw or {}))
    return EnvelopeCheck(
        action=decision.action,
        reason=decision.reason,
        subject=decision.subject or base["subject"],
        relation=decision.relation or base["relation"],
        obj=decision.obj or base["obj"],
        valid_from=vf_text,
        valid_to=vt_text,
        source=source,
        stripped=stripped,
        eat=decision.to_dict(),
    )


# ── interval conflicts against the real Titanos fact log ─────────────


def _titanos_class(titanos: Any) -> Any:
    return type(titanos)


def _parse_bound(titanos: Any, value: Any) -> Optional[datetime]:
    parser = getattr(_titanos_class(titanos), "_parse_temporal", None)
    if callable(parser):
        return parser(value)
    return _parse_iso(str(value)) if value not in (None, "") else None


def _fields(titanos: Any, fact: tuple) -> tuple:
    helper = getattr(_titanos_class(titanos), "_fact_fields", None)
    if callable(helper):
        return helper(fact)
    if len(fact) >= 5:
        return fact[0], fact[1], fact[2], fact[3], fact[4]
    return fact[0], fact[1], fact[2], None, None


def _overlap(
    a_from: Optional[datetime],
    a_to: Optional[datetime],
    b_from: Optional[datetime],
    b_to: Optional[datetime],
) -> bool:
    """Half-open [from, to) overlap. None is an open end."""
    starts_before_b_ends = b_to is None or a_from is None or a_from < b_to
    b_starts_before_a_ends = a_to is None or b_from is None or b_from < a_to
    return starts_before_b_ends and b_starts_before_a_ends


def _bounded(valid_from: Any, valid_to: Any) -> bool:
    return valid_from not in (None, "") or valid_to not in (None, "")


def stored_conflicts(titanos: Any, check: EnvelopeCheck) -> list[dict[str, Any]]:
    """Stored facts that compete with this claim inside its window.

    Matches the rule Titanos uses at query time
    (``_explicit_temporal_conflict``): only explicitly bounded facts
    compete. Unbounded multi-valued relations such as ``parent_of`` are
    not conflicts.
    """
    if not _bounded(check.valid_from, check.valid_to):
        return []
    facts = getattr(titanos, "facts", None) or []
    a_from = _parse_bound(titanos, check.valid_from)
    a_to = _parse_bound(titanos, check.valid_to)
    out: list[dict[str, Any]] = []
    for fact in facts:
        subject, relation, obj, valid_from, valid_to = _fields(titanos, fact)
        if subject != check.subject or relation != check.relation or obj == check.obj:
            continue
        if not _bounded(valid_from, valid_to):
            continue
        b_from = _parse_bound(titanos, valid_from) if valid_from not in (None, "") else None
        b_to = _parse_bound(titanos, valid_to) if valid_to not in (None, "") else None
        if _overlap(a_from, a_to, b_from, b_to):
            out.append(
                {
                    "subject": subject,
                    "relation": relation,
                    "obj": obj,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "where": "titanos",
                }
            )
    return out


def _already_stored(titanos: Any, check: EnvelopeCheck) -> bool:
    for fact in getattr(titanos, "facts", None) or []:
        subject, relation, obj, valid_from, valid_to = _fields(titanos, fact)
        if (subject, relation, obj) == check.key() and (valid_from or None) == (
            check.valid_from or None
        ) and (valid_to or None) == (check.valid_to or None):
            return True
    return False


def _batch_conflicts(checks: list[EnvelopeCheck], titanos: Any) -> None:
    """Mark every pair of bounded, overlapping, competing claims CONFLICT."""
    for i, left in enumerate(checks):
        if left.action not in ("accept", "conflict"):
            continue
        for right in checks[i + 1:]:
            if right.action not in ("accept", "conflict"):
                continue
            if (left.subject, left.relation) != (right.subject, right.relation):
                continue
            if left.obj == right.obj:
                continue
            if not (_bounded(left.valid_from, left.valid_to) and _bounded(right.valid_from, right.valid_to)):
                continue
            if _overlap(
                _parse_bound(titanos, left.valid_from),
                _parse_bound(titanos, left.valid_to),
                _parse_bound(titanos, right.valid_from),
                _parse_bound(titanos, right.valid_to),
            ):
                for mine, other in ((left, right), (right, left)):
                    mine.action = "conflict"
                    mine.reason = "overlapping_competing_claim"
                    mine.conflicts_with.append(
                        {
                            "subject": other.subject,
                            "relation": other.relation,
                            "obj": other.obj,
                            "valid_from": other.valid_from,
                            "valid_to": other.valid_to,
                            "where": "batch",
                        }
                    )


# ── commit through Zeus ───────────────────────────────────────────────


def eat_commit_envelopes(
    envelopes: Iterable[Any],
    *,
    titanos: Any,
    ask_fn: Optional[Callable[[str, str], Any]] = None,
    use_council: bool = True,
    use_athena: bool = False,
    profile: str = "personal",
    verifier_ctx: Optional[dict[str, Any]] = None,
    eat_kw: Optional[dict[str, Any]] = None,
    notes: Any = None,
) -> dict[str, Any]:
    """Eat a batch of envelopes and commit the survivors through Zeus.

    ``titanos`` is a Titanos instance (or anything with the same
    ``learn(s, r, o, *, valid_from, valid_to)`` signature and ``facts``
    log). Nothing is written unless every reviewer from
    ``default_reviewers`` approves. ``notes`` is an optional
    ``HadesNotes``; one summary line is appended (counts only).
    """
    from resileos.harness.separated import SeparatedCycle, default_reviewers, zeus_head

    checks = [check_envelope(item, eat_kw=eat_kw) for item in envelopes]
    for check in checks:
        if check.action != "accept":
            continue
        found = stored_conflicts(titanos, check)
        if found:
            check.action = "conflict"
            check.reason = "overlaps_stored_fact"
            check.conflicts_with.extend(found)
        elif _already_stored(titanos, check):
            check.action = "abstain"
            check.reason = "already_stored"
    _batch_conflicts(checks, titanos)

    accepted = [check for check in checks if check.action == "accept"]
    head: dict[str, Any] = {"applied": False, "reason": "nothing accepted", "verdicts": []}
    if accepted:
        sc = SeparatedCycle(id_prefix="eat-envelope")

        def writer(**_kwargs: Any) -> dict[str, Any]:
            return {
                "status": "ok",
                "hub_rows": [
                    {"subject": c.subject, "relation": c.relation, "obj": c.obj}
                    for c in accepted
                ],
            }

        proposal = sc.propose("eat", writer, action_type="eat")
        proposal.metadata["temporal_bounds"] = [
            (c.valid_from, c.valid_to) for c in accepted
        ]
        proposal.metadata["envelope_version"] = ENVELOPE_VERSION
        bounds = list(proposal.metadata["temporal_bounds"])
        cursor = {"i": 0}

        def learn(subject: str, relation: str, obj: str) -> None:
            index = cursor["i"]
            cursor["i"] += 1
            valid_from, valid_to = bounds[index] if index < len(bounds) else (None, None)
            titanos.learn(subject, relation, obj, valid_from=valid_from, valid_to=valid_to)

        reviewers = default_reviewers(
            sc,
            ask_fn=ask_fn,
            use_council=use_council,
            use_athena=use_athena,
            profile=profile,
            verifier_ctx=verifier_ctx,
        )
        head = zeus_head(proposal, reviewers, learn, cycle=sc)
        if head.get("applied"):
            for check in accepted:
                check.action = "committed"
                check.reason = "all reviewers approved"
        else:
            for check in accepted:
                check.action = "held"
                check.reason = str(head.get("reason") or "reviewer rejected")

    counts: dict[str, int] = {}
    for check in checks:
        counts[check.action] = counts.get(check.action, 0) + 1
    summary = {
        "version": ENVELOPE_VERSION,
        "committed": int(counts.get("committed", 0)),
        "counts": counts,
        "reviewers": [v.get("reviewer") for v in head.get("verdicts", []) if isinstance(v, dict)],
        "applied": bool(head.get("applied")),
    }
    if notes is not None:
        notes.append(
            lesson=(
                f"eat envelope batch: committed={summary['committed']} "
                f"conflict={counts.get('conflict', 0)} abstain={counts.get('abstain', 0)} "
                f"reject={counts.get('reject', 0)} held={counts.get('held', 0)}"
            ),
            verified=bool(head.get("applied")),
            outcome="verified" if head.get("applied") else "rejected" if accepted else "not_required",
            metrics={key: float(value) for key, value in counts.items()},
        )
    return {
        "summary": summary,
        "results": [check.to_dict() for check in checks],
        "head": head,
    }


__all__ = [
    "ATTENTION_KEYS",
    "ENVELOPE_VERSION",
    "EnvelopeCheck",
    "check_envelope",
    "eat_commit_envelopes",
    "stored_conflicts",
    "strip_attention",
]
