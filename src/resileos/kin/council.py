"""
Council of stores — federated query across hub namespaces.

Deterministic arbitration with explicit precedence and provenance.
Does not invent values. Conflicts are surfaced (dim.conflict).
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
    answers: list[HubAnswer] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

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
            "answers": [a.to_dict() for a in self.answers],
            "conflicts": list(self.conflicts),
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


def council_query(
    subject: str,
    relation: str,
    ask_fn: Callable[[str, str], Any],
    *,
    profile: str = "personal",
    hubs: Optional[tuple[str, ...]] = None,
) -> CouncilResult:
    """
    Query multiple hub-scoped subjects; arbitrate by profile precedence.

    ask_fn(subject, relation) -> value | list | None
    """
    order = PRECEDENCE.get(profile, PRECEDENCE["personal"])
    if hubs is None:
        hubs = order
    pairs = expand_subjects(subject, hubs)
    answers: list[HubAnswer] = []
    present: list[HubAnswer] = []
    for hub, subj in pairs:
        try:
            val = ask_fn(subj, relation)
        except Exception:
            val = None
        is_present = val is not None and val != [] and val != ""
        ans = HubAnswer(
            hub=hub,
            subject=subj,
            relation=relation,
            value=val if is_present else None,
            present=is_present,
        )
        answers.append(ans)
        if is_present:
            present.append(ans)

    result = CouncilResult(
        subject=subject,
        relation=relation,
        answers=answers,
        profile=profile,
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

    unique = {}
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
