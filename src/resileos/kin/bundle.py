"""Kin bundle — align Iris / Metis / Hermes / Eat with AgencyGroup + Zeus.

Harness layer integrated: risk gates, confidence routing, verify-on-stop,
budget/stuck guards, residual consistency, Apollo outer sensor, and the
verification-requirement classification (zero-match rule, 2026-11-09).

Hades checkpoint: verified cycles write a durable checkpoint (lesson +
control_state + residual_hash). The write is non-blocking; a failed save
does not break the cycle.
"""
from __future__ import annotations

from resileos.ui.recursive_improve import recursive_step
from resileos.ui.success_improve import improve_cycle
from resileos.kin.apollo import apollo_cycle

from resileos.ui.attach_scale import attach_scale

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from resileos.kin.eat import EatDecision, eat_and_learn, eat_filter
from resileos.kin.hades import Hades, make_hades
from resileos.kin.hermes import HermesBudget, make_hermes_navigator
from resileos.kin.iris import IrisReport, make_iris_observer
from resileos.kin.metis import MetisPolicy, make_metis_organizer

# Harness integration
from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    apollo_success,
    budget_and_stuck_guard,
    evidence_attach,
    guide_load,
    residual_consistency,
    risk_classify,
    verification_required,
    verify_on_stop,
)
from resileos.harness.cascade import CascadeRouter
from resileos.kin.moirai import checkpoint_allowed, cut_owned


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
    control: Optional[ControlPacket] = None

    def cycle(
        self,
        metrics: Optional[dict[str, Any]] = None,
        agency_group: Any = None,
        *,
        apply_policy: bool = True,
        residual_packet: Any = None,
        aphrodite_state: Any = None,
    ) -> tuple[IrisReport, MetisPolicy, dict]:
        """Iris -> Metis + full harness guards and outer verification."""
        if self.control is None:
            self.control = ControlPacket(id="kin-cycle")

        guide_load(
            ["docs/harness/CONSTRAINTS.md", "docs/harness/AGENTS.md"],
            self.control.to_dict(),
        )

        topics: list[Any] = []
        if residual_packet is not None:
            if isinstance(residual_packet, dict):
                topics = list(residual_packet.get("topics") or [])
            else:
                topics = list(getattr(residual_packet, "topics", None) or [])
        care: dict[str, float] = {}
        peak = 1.0
        if aphrodite_state is not None:
            for topic in topics:
                mult = float(aphrodite_state.care_multiplier(str(topic)))
                care[str(topic)] = mult
                peak = max(peak, mult)
        view = self.control.to_dict()
        if peak > 1.0:
            self.control.append({"event": "aphrodite_care", "peak": peak, "care": care})
            view = self.control.to_dict()
            budgets = dict(view.get("budget_remaining") or {})
            if "cost" in budgets:
                budgets["cost"] = float(budgets["cost"]) * peak
                view["budget_remaining"] = budgets

        guard = budget_and_stuck_guard(view)
        if not guard["ok"]:
            cut_owned(self.control.id, reason=guard["reason"])
            self.control.append({"event": "guard_fail", "reason": guard["reason"]})
            report = self.observe(metrics=metrics, agency_group=agency_group)
            policy = self.organize(report)
            self.last_report = report
            self.last_policy = policy
            return report, policy, {
                "harness": {"guard": guard, "verified": False}
            }

        report = self.observe(metrics=metrics, agency_group=agency_group)
        policy = self.organize(report)
        self.last_report = report
        self.last_policy = policy

        if apply_policy and agency_group is not None:
            apply_metis_to_agency(policy, agency_group)

        consistency = residual_consistency(self.control.to_dict())
        packet_hash = None
        if residual_packet is not None:
            if isinstance(residual_packet, dict):
                packet_hash = residual_packet.get("packet_hash")
            else:
                packet_hash = getattr(residual_packet, "packet_hash", None)
            if packet_hash:
                evidence_attach(
                    {"packet_hash": packet_hash},
                    "residual_core",
                    self.control.to_dict(),
                )
        if peak > 1.0 and not packet_hash:
            consistency = {
                "consistent": False,
                "reason": "high-care topic requires a residual hash",
                "scars": list(consistency.get("scars") or []),
            }

        verification = verification_required("kin_cycle")
        apollo = apollo_success({
            "status": "ok" if consistency.get("consistent") else "scarred"
        })
        v = verify_on_stop(
            self.control.to_dict(),
            apollo,
            require_evidence=verification["requires_verification"],
        )
        self.control.verified = v["verified"]
        self.control.append({
            "event": "verify",
            "result": v,
            "consistency": consistency,
            "verification_required": verification,
        })

        # Hades checkpoint on verified cycles only. The lesson is the
        # only thing that crosses attempts. A failed save does not
        # abort the cycle.
        checkpoint_id = None
        lesson = None
        checkpoint_error = None
        fragment = None
        if v["verified"]:
            rank = getattr(self.last_policy, "depth", None)
            if rank is None:
                rank = getattr(self.last_policy, "rank", "?")
            lesson = (
                f"kin_cycle turn={self.control.turn} "
                f"verified=True rank={rank}"
            )
            allowed, why = checkpoint_allowed(
                self.control.id,
                residual_consistent=bool(consistency.get("consistent")),
            )
            if not allowed:
                checkpoint_error = why
            else:
                extra = None
                if aphrodite_state is not None:
                    fragment = aphrodite_state.advance("kin_cycle", verified=True)
                    extra = {"aphrodite": aphrodite_state.to_dict()}
                try:
                    if getattr(self, "_hades", None) is None:
                        self._hades = make_hades()
                    ckpt = self._hades.save(self.control, lesson=lesson, extra=extra)
                    checkpoint_id = ckpt.id
                    lesson = ckpt.lesson
                except Exception as exc:
                    checkpoint_error = str(exc)

        harness_summary = {
            "verified": v["verified"],
            "reason": v["reason"],
            "verification_required": verification["requires_verification"],
            "consistency": consistency,
            "apollo": apollo,
            "budget": self.control.budget_remaining,
            "guides": self.control.guides_loaded,
        }
        if care:
            harness_summary["care_multipliers"] = care
        if v["verified"] and fragment:
            harness_summary["tutorial_fragment"] = fragment
        if checkpoint_id is not None:
            harness_summary["checkpoint"] = checkpoint_id
            harness_summary["lesson"] = lesson
        if checkpoint_error is not None:
            harness_summary["checkpoint_error"] = checkpoint_error
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
