"""
Eat filter — external signal → accept | reject | abstain → optional learn.

This is the operational analog of a *filter*: quality and structure gates
before anything becomes durable store truth. It does not model emotion or
consciousness; it enforces:

  - structured triples only for learn
  - reject empty / too-long / reserved system subjects (unless allowed)
  - abstain when confidence flag is low or claim is free text without parse

Pairs with seed.record_learn when accepted.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

_TRIPLE_LINE = re.compile(
    r"^\s*(\S+)\s+(\S+)\s+(.+?)\s*$",
)


@dataclass
class EatDecision:
    action: str  # accept | reject | abstain
    subject: str = ""
    relation: str = ""
    obj: str = ""
    reason: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_triple(text: str) -> Optional[tuple[str, str, str]]:
    text = (text or "").strip()
    if not text:
        return None
    # JSON-ish dict
    if text.startswith("{") and "subject" in text:
        try:
            import json

            d = json.loads(text)
            s, r, o = d.get("subject"), d.get("relation"), d.get("obj") or d.get("object")
            if s and r and o is not None:
                return str(s), str(r), str(o)
        except Exception:
            pass
    # WH-questions and long prose are not triples
    low = text.lower()
    if low.endswith("?") or low.startswith(
        ("what ", "who ", "why ", "how ", "when ", "where ", "is ", "are ")
    ):
        return None
    m = _TRIPLE_LINE.match(text)
    if m:
        # relation should look like a token (no spaces in group 2 already)
        rel = m.group(2)
        if len(rel) > 64:
            return None
        return m.group(1), rel, m.group(3)
    parts = text.split()
    # Require short subject/relation tokens; object may be multi-word
    if len(parts) >= 3 and len(parts[0]) <= 64 and len(parts[1]) <= 64:
        if parts[1].isalpha() or "_" in parts[1]:
            return parts[0], parts[1], " ".join(parts[2:])
    return None


def eat_filter(
    claim: str | dict[str, Any],
    *,
    max_obj_len: int = 500,
    allow_sys: bool = False,
    min_parts: int = 3,
) -> EatDecision:
    """
    Filter a candidate claim before it can enter Titanos.

    accept  → well-formed triple, safe subject
    reject  → malformed or forbidden
    abstain → cannot decide (e.g. prose without structure)
    """
    source = "dict" if isinstance(claim, dict) else "text"
    if isinstance(claim, dict):
        s = str(claim.get("subject") or "").strip()
        r = str(claim.get("relation") or "").strip()
        o = claim.get("obj", claim.get("object", ""))
        o = str(o).strip() if o is not None else ""
        if not s or not r or not o:
            return EatDecision(
                action="reject",
                reason="missing_subject_relation_or_obj",
                source=source,
            )
        parsed = (s, r, o)
    else:
        parsed = _parse_triple(str(claim))
        if parsed is None:
            return EatDecision(
                action="abstain",
                reason="unstructured_prose",
                source=source,
            )

    s, r, o = parsed
    if len(o) > max_obj_len:
        return EatDecision(
            action="reject",
            subject=s,
            relation=r,
            obj=o[:80],
            reason="obj_too_long",
            source=source,
        )
    if s.startswith("sys:") and not allow_sys:
        return EatDecision(
            action="reject",
            subject=s,
            relation=r,
            obj=o,
            reason="sys_subject_forbidden",
            source=source,
        )
    if not r.replace("_", "").isalnum():
        return EatDecision(
            action="reject",
            subject=s,
            relation=r,
            obj=o,
            reason="relation_not_token",
            source=source,
        )
    return EatDecision(
        action="accept",
        subject=s,
        relation=r,
        obj=o,
        reason="ok",
        source=source,
    )


def eat_and_learn(
    claim: str | dict[str, Any],
    learn_fn: Callable[[str, str, str], Any],
    *,
    user_id: str = "",
    seed_record: bool = True,
    **filter_kw: Any,
) -> EatDecision:
    """
    Run eat_filter; on accept call learn_fn(subject, relation, obj).

    learn_fn is injected (Titanos.learn or API wrapper) so tests stay pure.
    """
    decision = eat_filter(claim, **filter_kw)
    if decision.action != "accept":
        return decision
    try:
        learn_fn(decision.subject, decision.relation, decision.obj)
    except Exception as e:
        decision.action = "reject"
        decision.reason = f"learn_failed:{e}"
        return decision
    if seed_record and user_id:
        try:
            from resileos.seed.evolution import record_learn

            record_learn(
                user_id, decision.subject, decision.relation, decision.obj
            )
        except Exception:
            pass
    return decision
