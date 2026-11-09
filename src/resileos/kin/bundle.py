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
            self.last_report =
