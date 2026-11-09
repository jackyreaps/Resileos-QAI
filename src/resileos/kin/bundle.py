"""
Kin bundle — align Iris / Metis / Hermes / Eat with AgencyGroup + Zeus.
Harness layer integrated: risk gates, confidence routing, verify-on-stop,
budget/stuck guards, residual consistency, and Apollo as outer sensor.
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

# Harness integration
from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    budget_and_stuck_guard,
    residual_consistency,
    verify_on_stop,
    risk_classify,
    guide_load,
    evidence_attach,
    apollo_success,
)
from resileos.harness.cascade import CascadeRouter


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
    # Harness state (attached control layer)
    control: Optional[ControlPacket] = None

    def cycle(
        self,
        metrics: Optional[dict[str, Any]] = None,
        agency_group: Any = None,
        *,
        apply_policy: bool = True,
        residual_packet: Any = None,  # optional residual Packet for consistency
    ) -> tuple[IrisReport, MetisPolicy, dict]:
        """Iris → Metis + full harness guards and outer verification."""
        # Ensure control packet exists
        if self.control is None:
            self.control = ControlPacket(id="kin-cycle")

        # 1. Hierarchical guides (JIT context)
        guide_load(["docs/harness/CONSTRAINTS.md", "docs/harness/AGENTS.md"], self.control.to_dict())

        # 2. Budget + stuck guard
        guard = budget_and_stuck_guard(self.control.to_dict())
        if not guard["ok"]:
            self.control.append({"event": "guard_fail", "reason": guard["reason"]})
            # Still produce Iris/Metis but mark unverified
            report = self.observe(metrics=metrics, agency_group=agency_group)
            policy = self.organize(report)
            self.last_report = report
            self.last_policy = policy
            return report, policy, {"harness": {"guard": guard, "verified": False}}

        # 3. Iris observe → Metis organize
        report = self.observe(metrics=metrics, agency_group=agency_group)
        policy = self.organize(report)
        self.last_report = report
        self.last_policy = policy

        if apply_policy and agency_group is not None:
            apply_metis_to_agency(policy, agency_group)

        # 4. Residual consistency sensor (if residual Packet supplied)
        consistency = residual_consistency(self.control.to_dict())
        if residual_packet is not None:
            # Attach residual hash as evidence
            evidence_attach(
                {"packet_hash": getattr(residual_packet, "packet_hash", None)},
                "residual_core",
                self.control.to_dict(),
            )

        # 5. Outer verification (Apollo + verify-on-stop)
        apollo = apollo_success({"status": "ok" if consistency.get("consistent") else "scarred"})
        v = verify_on_stop(self.control.to_dict(), apollo)
        self.control.verified = v["verified"]
        self.control.append({"event": "verify", "result": v, "consistency": consistency})

        harness_summary = {
            "verified": v["verified"],
            "consistency": consistency,
            "apollo": apollo,
            "budget": self.control.budget_remaining,
            "guides": self.control.guides_loaded,
        }
        return report, policy, harness_summary


def apply_metis_to_agency(policy: MetisPolicy, agency_group: Any) -> list[str]:
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
        control=ControlPacket(id="kin-bundle"),
    )


def register_answer_child(
    agency_group: Any,
    name: str,
    handler: Callable[..., Any],
    weight: float = 1.0,
) -> Any:
    return agency_group.add_child(name, handler, weight=weight)


def register_declining_kin(
    agency_group: Any,
    bundle: KinBundle,
    *,
    weight: float = 0.01,
) -> None:
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
    return improve_cycle(facts, subject=subject, eat_fn=eat_fn)


def bundle_apollo(facts: list, subject: str = "world:apollo", eat_fn=None, art: bool = False) -> dict:
    return apollo_cycle(facts, subject=subject, eat_fn=eat_fn, art=art)
