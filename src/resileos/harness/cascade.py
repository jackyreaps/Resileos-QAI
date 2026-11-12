"""Cascade router integrating fan-out with residual retrieval and Apollo."""
from typing import Any, Callable, Dict, Optional

from .tools import apollo_success, confidence_route, risk_classify, verify_on_stop


def _default_residual(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Use rows the fan-out already matched. Otherwise abstain."""
    evidence = []
    if isinstance(decision, dict) and isinstance(decision.get("evidence"), list):
        evidence = list(decision["evidence"])
    if evidence:
        return {"status": "ok", "rows": evidence}
    return {
        "status": "ABSTAINED",
        "rows": [],
        "reason": "no residual rows for this choice",
    }


class CascadeRouter:
    def __init__(
        self,
        residual_fn: Optional[Callable] = None,
        apollo_fn: Optional[Callable] = None,
    ):
        self.residual_fn = residual_fn or _default_residual
        self.apollo_fn = apollo_fn or apollo_success

    def _resolve(self, route: str, decision: Dict[str, Any], packet: Dict[str, Any]) -> Dict[str, Any]:
        result = self.residual_fn(decision)
        if not isinstance(result, dict):
            result = {"status": "ABSTAINED", "rows": [], "reason": "residual result was not a dict"}
        status = str(result.get("status") or "").strip().lower()
        if status in {"", "abstained", "residual_stub", "unavailable"}:
            packet["verified"] = False
            return {
                "route": route,
                "decision": decision,
                "result": result,
                "verify": {"verified": False, "reason": "no residual support"},
                "packet": packet,
            }
        apollo = self.apollo_fn(result)
        verdict = verify_on_stop(packet, apollo)
        packet["verified"] = verdict["verified"]
        return {
            "route": route,
            "decision": decision,
            "result": result,
            "apollo": apollo,
            "verify": verdict,
            "packet": packet,
        }

    def route(self, question: str, options: list, packet: Dict[str, Any]) -> Dict[str, Any]:
        risk = risk_classify(question, packet)
        if risk["risk_class"] == "deny":
            packet["verified"] = False
            return {"route": "deny", "risk": risk, "packet": packet}

        from .tools import decision_fanout

        decision = decision_fanout(question, options, packet)
        routed = confidence_route(decision)
        packet["confidence"] = routed["probability"]
        packet["risk_class"] = risk["risk_class"]

        if routed["route"] == "residual_or_apollo":
            return self._resolve("residual", decision, packet)
        if routed["route"] == "cascade":
            return self._resolve("cascade", decision, packet)
        packet["verified"] = False
        return {
            "route": "escalate",
            "decision": decision,
            "verify": {"verified": False, "reason": "below residual support"},
            "packet": packet,
        }
