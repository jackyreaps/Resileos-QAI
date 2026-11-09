"""Council of stores — federated query across hub namespaces.

Deterministic arbitration with explicit precedence and provenance.
Does not invent values. Conflicts are surfaced (dim.conflict).

Temporal extension (RES-332):

    `council_query(..., as_of=...)` filters each hub's answer at
    query time. Each `HubAnswer` carries the `as_of` it was resolved
    at, plus `multi_value=True` when the hub returned >1 chronos-valid
    facts for the same (s, r) at that moment.

    `multi_value` is not automatically a conflict. It is legitimate
    for multi-valued relations (Cronus --parent_of--> six children)
    AND it is the signal for a temporal conflict (overlapping
    validity). Council cannot distinguish these without the fact
    list; it surfaces the flag and lets the caller decide.

    `ask_fn` is now called with `as_of=` when provided. If the
    function does not accept `as_of` (legacy callers), the call falls
    back to the two-argument form and the answer is not
    temporal-filtered. A deprecation-safe fallback, not a silent one:
    the caller can check `HubAnswer.as_of` to see whether the filter
    applied.
"""
from __future__ import annotations

from resileos.ui.recursive_improve import recursive_step

from resileos.ui.scale_address import scale_address

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from resileos.kin.frames import (
    CAT_CONFLICT,
    CAT_MULTI,
    FRAME_ABSTAINED,
    FRAME_EXACT,
    hub_category,
)

# Precedence profiles: first listed hub wins for that profile
PRECEDENCE = {
    "personal": ("user", "world", "org", "default"),
    "policy": ("org", "world", "user", "default"),
    "world": ("world", "org", "user", "default"),
}


@dataclass
class HubAnswer:
    hub: str
    subject: str
    relation: str
    value: Any
    present: bool
    as_of: Optional[str] = None         # NEW — moment the filter used
    multi_value: bool = False            # NEW — value was a multi-element list
    as_of_applied: bool = False          # NEW — ask_fn accepted as_of=

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilResult:
    subject: str
    relation: str
    value: Any = None
    status: str = "ABSTAINED"  # ACCEPTED | CONFLICT | ABSTAINED
    frame: str = FRAME_ABSTAINED
    dim: str = CAT_MULTI
    winner_hub: str = ""
    profile: str = "personal"
    as_of: Optional[str] = None          # NEW — moment of the arbitration
    answers: list[HubAnswer] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    multi_value_hubs: list[str] = field(default_factory=list)  # NEW

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "relation": self.relation,
            "value": self.value,
            "status": self.status,
            "frame": self.frame,
            "dim": self.dim,
            "winner_hub": self.winner_hub,
            "profile": self.profile,
            "as_of": self.as_of,
            "answers": [a.to_dict() for a in self.answers],
            "conflicts": list(self.conflicts),
            "multi_value_hubs": list(self.multi_value_hubs),
        }


def _hub_key(name: str) -> str:
    n = (name or "default").lower()
    if n in ("user", "world", "org", "default"):
        return n
    return "default"


def expand_subjects(subject: str, hubs: tuple[str, ...]) -> list[tuple[str, str]]:
    """
    Map bare subject to hub-qualified subjects when not already prefixed.
    Returns list of (hub, subject_to_query).
    """
    s = (subject or "").strip()
    if s.startswith(("user:", "world:", "org:", "sys:")):
        return [(_hub_key(hub_category(s).replace("dim.", "")), s)]
    out = []
    for h in hubs:
        if h == "default":
            out.append(("default", s))
        else:
            out.append((h, f"{h}:{s}"))
    return out


def _call_ask(
    ask_fn: Callable[..., Any],
    subject: str,
    relation: str,
    as_of: Optional[str],
) -> tuple[Any, bool]:
    """Call ask_fn with as_of when provided; fall back to (s, r) if the
    function does not accept the keyword.

    Returns (value, as_of_applied).
    """
    if as_of is not None:
        try:
            return ask_fn(subject, relation, as_of=as_of), True
        except TypeError:
            # Legacy ask_fn without as_of kwarg — fall back
            pass
    try:
        return ask_fn(subject, relation), False
    except Exception:
        return None, False


def council_query(
    subject: str,
    relation: str,
    ask_fn: Callable[..., Any],
    *,
    profile: str = "personal",
    hubs: Optional[tuple[str, ...]] = None,
    as_of: Optional[str] = None,
) -> CouncilResult:
    """
    Query multiple hub-scoped subjects; arbitrate by profile precedence.

    ask_fn(subject, relation, as_of=...) -> value | list | None
    If ask_fn does not accept as_of, the call falls back to
    ask_fn(subject, relation) and the answer is not temporal-filtered
    (as_of_applied=False on the resulting HubAnswer).
    """
    order = PRECEDENCE.get(profile, PRECEDENCE["personal"])
    if hubs is None:
        hubs = order
    pairs = expand_subjects(subject, hubs)
    answers: list[HubAnswer] = []
    present: list[HubAnswer] = []
    multi_value_hubs: list[str] = []

    for hub, subj in pairs:
        val, as_of_applied = _call_ask(ask_fn, subj, relation, as_of)
        is_present = val is not None and val != [] and val != ""
        is_multi = isinstance(val, list) and len(val) > 1
        ans = HubAnswer(
            hub=hub,
            subject=subj,
            relation=relation,
            value=val if is_present else None,
            present=is_present,
            as_of=as_of,
            multi_value=is_multi,
            as_of_applied=as_of_applied,
        )
        answers.append(ans)
        if is_present:
            present.append(ans)
            if is_multi and hub not in multi_value_hubs:
                multi_value_hubs.append(hub)

    result = CouncilResult(
        subject=subject,
        relation=relation,
        answers=answers,
        profile=profile,
        as_of=as_of,
        multi_value_hubs=multi_value_hubs,
    )
    if not present:
        result.status = "ABSTAINED"
        result.frame = FRAME_ABSTAINED
        result.dim = CAT_MULTI
        return result

    # Normalize values for conflict detection
    def norm(v: Any) -> str:
        if isinstance(v, list):
            return "|".join(sorted(str(x) for x in v))
        return str(v)

    unique: dict[str, list[HubAnswer]] = {}
    for a in present:
        unique.setdefault(norm(a.value), []).append(a)

    if len(unique) > 1:
        result.status = "CONFLICT"
        result.frame = FRAME_ABSTAINED
        result.dim = CAT_CONFLICT
        result.conflicts = [
            {"value": k, "hubs": [x.hub for x in vs]}
            for k, vs in unique.items()
        ]
        # Still report precedence winner for UX, marked conflict
        for h in order:
            for a in present:
                if a.hub == h:
                    result.value = a.value
                    result.winner_hub = a.hub
                    return result
        result.value = present[0].value
        result.winner_hub = present[0].hub
        return result

    # Single consensus value — pick by precedence
    for h in order:
        for a in present:
            if a.hub == h:
                result.value = a.value
                result.winner_hub = a.hub
                result.status = "ACCEPTED"
                result.frame = FRAME_EXACT
                result.dim = CAT_MULTI
                return result
    a = present[0]
    result.value = a.value
    result.winner_hub = a.hub
    result.status = "ACCEPTED"
    result.frame = FRAME_EXACT
    result.dim = CAT_MULTI
    return result


def council_with_address(result, subject: str = "") -> dict:
    """Attach a scale address to a council result."""
    addr = scale_address(subject=subject or "council")
    base = result.to_dict() if hasattr(result, "to_dict") else {"result": str(result)}
    base["scale"] = {"address": addr["embed"], "gate": addr["gate"]}
    return base


def council_recursive(facts: list, subject: str = "world:kin") -> dict:
    """Run one recursive improve step from this kin."""
    return recursive_step(facts, subject=subject)
