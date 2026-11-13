"""Metis — organizer kin. Policy flags only; cannot learn world triples."""
from __future__ import annotations

from resileos.ui.recursive_improve import recursive_step

from resileos.ui.attach_scale import attach_scale

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import re

from resileos.kin.hermes import (
    HEPHAESTUS_MAX_DEPTH,
    HEPHAESTUS_MAX_ITEMS,
    HermesBudget,
)
from resileos.kin.iris import IrisReport

_MULTI_HOP = re.compile(
    r"(?i)(?:\bparent of the\b|\bgrand(?:parent|child|mother|father)?\b|"
    r"\bchain\b|\bvia\b|\band then\b|\bwho is the \w+ of the\b|"
    r"\bmulti[- ]hop\b)"
)


@dataclass
class MetisPolicy:
    """Routing / budget policy derived from Iris — not store mutations."""

    prefer_structured: bool = True
    allow_mouth: bool = False
    hermes_depth_cap: int = 2
    disable_children: list[str] = field(default_factory=list)
    enable_children: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def hermes_budget_for(text: str, policy: MetisPolicy | None = None) -> HermesBudget:
    """Widen Hermes for a multi-hop question and keep a simple lookup tight.

    Both sit inside the Hephaestus caps. The returned budget does not
    invent hops and does not change an exact ``Titanos.chain`` call.
    """
    multi = bool(_MULTI_HOP.search(text or ""))
    if multi:
        depth, items = 4, 12
    else:
        depth, items = 1, 4
    if policy is not None:
        depth = min(depth, max(1, int(policy.hermes_depth_cap)))
    depth = min(HEPHAESTUS_MAX_DEPTH, max(1, int(depth)))
    items = min(HEPHAESTUS_MAX_ITEMS, max(1, int(items)))
    return HermesBudget(max_depth=depth, max_items=items)


def clip_hops(relations: list[str], budget: HermesBudget) -> list[str]:
    """Keep as many hops as the budget's depth allows."""
    depth = min(HEPHAESTUS_MAX_DEPTH, max(1, int(budget.max_depth)))
    return list(relations)[:depth]


def make_metis_organizer(*, miss_threshold: float = 0.3):
    """
    organize(report: IrisReport) -> MetisPolicy

    Constraints (RES-334):
      - no learn on world facts
      - no bypass of NONE_CHANNEL / abstain
    """

    def organize(report: IrisReport) -> MetisPolicy:
        policy = MetisPolicy()
        if "low_hit_rate" in report.flags or "miss_dominant" in report.flags:
            policy.prefer_structured = True
            policy.allow_mouth = False
            policy.hermes_depth_cap = 1
            policy.reasons.append("tighten_on_misses")
        if "no_teaches" in report.flags:
            policy.reasons.append("encourage_teach_ux")
            policy.prefer_structured = True
        if report.hit_rate >= 0.7 and report.hits >= 5:
            policy.allow_mouth = True
            policy.hermes_depth_cap = 3
            policy.reasons.append("stable_hits_open_mouth")
        if report.eaten_children:
            policy.disable_children = list(report.eaten_children)
            policy.reasons.append("respect_eaten")
        return policy

    def handler(parent: Any, subject: str, relation: str, inverse: bool = False) -> Any:
        # Only answer reserved sys:agency reads if parent supports ask
        if not str(subject).startswith("sys:agency"):
            return None
        if relation in ("policy", "status") and parent is not None:
            ask = getattr(parent, "ask", None)
            if callable(ask):
                return ask(subject, relation)
        return None

    return organize, handler

def metis_recursive(facts: list, subject: str = "world:kin") -> dict:
    """Run one recursive improve step from this kin."""
    return recursive_step(facts, subject=subject)
