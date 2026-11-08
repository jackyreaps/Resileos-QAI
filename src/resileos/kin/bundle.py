"""
Kin bundle — align Iris / Metis / Hermes / Eat with AgencyGroup + Zeus.

Query routing stays with Zeus (or other answer children). Iris, Metis, and
Hermes are **side interfaces** (RES-334): they do not win subject/relation
routing. Optional low-weight handlers always return None so accidental
registration cannot override Zeus answers.

AgencyGroup.eat() remains the fitness prune for answer children.
eat_filter is the **ingest** gate for new claims (different verb).
"""
from __future__ import annotations

from resileos.ui.recursive_improve import recursive_step
from resileos.ui.success_improve import improve_cycle
from resileos.kin.apollo import apollo_cycle

from resileos.ui.attach_scale import attach_scale

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from resileos.kin.eat import EatDecision, eat_and_learn, eat_filter
from resileos.kin.hermes import HermesBudget, make_hermes_navigator
from resileos.kin.iris import IrisReport, make_iris_observer
from resileos.kin.metis import MetisPolicy, make_metis_organizer


@dataclass
class KinBundle:
    observe: Callable[..., IrisReport]
    organize: Callable[[IrisReport], MetisPolicy]
    navigate: Callable[..., list]
    iris_handler: Callable[..., Any]
    metis_handler: Callable[..., Any]
    hermes_handler: Callable[..., Any]
    last_report: Optional[IrisReport] = None
    last_policy: Optional[MetisPolicy] = None

    def cycle(
        self,
        metrics: Optional[dict[str, Any]] = None,
        agency_group: Any = None,
        *,
        apply_policy: bool = True,
    ) -> tuple[IrisReport, MetisPolicy]:
        """Iris observe → Metis organize → optional AgencyGroup weight hints."""
        report = self.observe(metrics=metrics, agency_group=agency_group)
        policy = self.organize(report)
        self.last_report = report
        self.last_policy = policy
        if apply_policy and agency_group is not None:
            apply_metis_to_agency(policy, agency_group)
        return report, policy


def apply_metis_to_agency(policy: MetisPolicy, agency_group: Any) -> list[str]:
    """
    Apply organizer hints without calling learn.

    - disable_children: mark inactive if present (does not delete)
    - does not invent fitness; respects already-eaten names from Iris
    """
    changed: list[str] = []
    children = getattr(agency_group, "children", None)
    if not isinstance(children, dict):
        return changed
    for name in policy.disable_children:
        ch = children.get(name)
        if ch is not None and getattr(ch, "active", False):
            ch.active = False
            eaten = getattr(agency_group, "eaten", None)
            if isinstance(eaten, list) and name not in eaten:
                eaten.append(name)
            changed.append(name)
    # re-normalize if API exists
    norm = getattr(agency_group, "_normalize_weights", None)
    if callable(norm):
        try:
            norm()
        except Exception:
            pass
    return changed


def build_kin_bundle(
    *,
    hermes_max_depth: int = 2,
    hermes_max_items: int = 8,
) -> KinBundle:
    observe, iris_h = make_iris_observer()
    organize, metis_h = make_metis_organizer()
    navigate, hermes_h = make_hermes_navigator(
        max_depth=hermes_max_depth, max_items=hermes_max_items
    )
    return KinBundle(
        observe=observe,
        organize=organize,
        navigate=navigate,
        iris_handler=iris_h,
        metis_handler=metis_h,
        hermes_handler=hermes_h,
    )


def register_answer_child(
    agency_group: Any,
    name: str,
    handler: Callable[..., Any],
    weight: float = 1.0,
) -> Any:
    """Register a fact-answering child (e.g. Zeus). Not for Iris/Metis/Hermes."""
    return agency_group.add_child(name, handler, weight=weight)


def register_declining_kin(
    agency_group: Any,
    bundle: KinBundle,
    *,
    weight: float = 0.01,
) -> None:
    """
    Optional: register declining handlers so snapshot lists kin names.
    They always return None — Zeus (or others) must hold real answer weight.
    """
    for name, h in (
        ("iris", bundle.iris_handler),
        ("metis", bundle.metis_handler),
        ("hermes", bundle.hermes_handler),
    ):
        if name not in getattr(agency_group, "children", {}):
            agency_group.add_child(name, h, weight=weight)

def bundle_scale(bundle: KinBundle) -> dict:
    return attach_scale({"children": len(getattr(bundle, "children", []) or [])}, "kin")

def bundle_recursive(facts: list, subject: str = "world:kin", eat_fn=None) -> dict:
    """Run one success-prioritized improve cycle from this kin."""
    return improve_cycle(facts, subject=subject, eat_fn=eat_fn)

def bundle_apollo(facts: list, subject: str = "world:apollo", eat_fn=None, art: bool = False) -> dict:
    return apollo_cycle(facts, subject=subject, eat_fn=eat_fn, art=art)
