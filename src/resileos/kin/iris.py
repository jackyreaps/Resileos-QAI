"""Iris — observer kin. Does not answer user facts."""
from __future__ import annotations

import re

from resileos.ui.recursive_improve import recursive_step

from resileos.ui.attach_scale import attach_scale

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

_GREETING = re.compile(
    r"(?i)^(?:hi|hello|hey|howdy|good morning|good afternoon|good evening|"
    r"thanks|thank you|bye|goodbye)\b"
)
_SMALLTALK = re.compile(
    r"(?i)\b(?:how are you|how's it going|whats up|what's up|nice to meet you)\b"
)
_META = re.compile(
    r"(?i)\b(?:who are you|what are you|what can you do|your name|how do you work)\b"
)
_MUTATE = re.compile(
    r"(?i)\b(?:remember|learn|write_file|apply_diff|git_commit)\b"
)
_TOOL = re.compile(r"(?i)^/(?:search|tool)\b")
_FACT = re.compile(
    r"(?i)\b(?:who is|what is|what are|when is|when did|when was|where is|which|whose)\b"
)

FAST_INTENTS = frozenset({"greeting", "smalltalk", "meta", "no_claim"})


def classify_intent(text: str, *, titanos: Any = None) -> str:
    """Classify a turn before the Kin cycle.

    Greetings, small talk, meta questions, and lines with no factual
    claim are fast. A stored value, a mutation, or a tool is not.
    """
    raw = (text or "").strip()
    low = raw.lower()
    if _TOOL.search(raw):
        return "tool"
    if _MUTATE.search(raw):
        return "mutate"
    factual = bool(_FACT.search(raw))
    if titanos is not None and not factual:
        try:
            from resileos.chat.router import fact_cue, hub_cue, teach_cue

            factual = bool(teach_cue(raw) or hub_cue(raw) or fact_cue(raw, titanos))
        except Exception:
            factual = factual
    if factual:
        return "factual"
    if _META.search(raw):
        return "meta"
    if _SMALLTALK.search(raw):
        return "smalltalk"
    if _GREETING.search(raw):
        return "greeting"
    return "no_claim"


@dataclass
class IrisReport:
    """Structured observation only — never store rows."""

    hits: int = 0
    misses: int = 0
    teaches: int = 0
    assets: int = 0
    sessions: int = 0
    hit_rate: float = 0.0
    active_children: list[str] = field(default_factory=list)
    eaten_children: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_iris_observer():
    """
    Side interface: observe(metrics=None, agency_group=None) -> IrisReport.

    Query handler always declines (None) so Iris never competes with Zeus
    for subject/relation answers.
    """

    def observe(
        metrics: Optional[dict[str, Any]] = None,
        agency_group: Any = None,
    ) -> IrisReport:
        m = dict(metrics or {})
        report = IrisReport(
            hits=int(m.get("hits", 0)),
            misses=int(m.get("misses", 0)),
            teaches=int(m.get("teaches", 0)),
            assets=int(m.get("assets", 0)),
            sessions=int(m.get("sessions", 0)),
            hit_rate=float(m.get("hit_rate", 0.0)),
        )
        if agency_group is not None:
            children = getattr(agency_group, "children", None) or {}
            if isinstance(children, dict):
                iterable = children.values()
            else:
                iterable = children
            for ch in iterable:
                name = getattr(ch, "name", str(ch))
                if getattr(ch, "active", True):
                    report.active_children.append(str(name))
                else:
                    report.eaten_children.append(str(name))
        # Filter flags — operational, not "emotion"
        if report.hit_rate < 0.3 and report.hits + report.misses >= 5:
            report.flags.append("low_hit_rate")
        if report.misses > report.hits and report.misses >= 3:
            report.flags.append("miss_dominant")
        if report.teaches == 0 and report.sessions >= 3:
            report.flags.append("no_teaches")
        if report.eaten_children:
            report.flags.append("children_eaten")
        return report

    def handler(parent: Any, subject: str, relation: str, inverse: bool = False) -> None:
        # Always decline fact queries
        return None

    return observe, handler

def iris_recursive(facts: list, subject: str = "world:kin") -> dict:
    """Run one recursive improve step from this kin."""
    return recursive_step(facts, subject=subject)
