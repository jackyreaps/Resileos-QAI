"""Cascade router integrating Jev-style fan-out with Resileos residual + Apollo."""
from typing import Any, Dict, Callable, Optional
from .tools import confidence_route, risk_classify, verify_on_stop, apollo_success

class CascadeRouter:
    def __init__(self, residual_fn: Optional[Callable] = None, apollo_fn: Optional[Callable] = None):
        self.residual_fn = residual_fn or (lambda x: {"status": "residual_stub"})
        self.apollo_fn = apollo_fn or apollo_success

    def route(self, question: str, options: list, packet: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Risk gate first
        risk = risk_classify(question, packet)
        if risk["risk_class"] == "deny":
            return {"route": "deny", "risk": risk, "packet": packet}

        # 2. Decision fan-out (Jev Choice)
        from .tools import decision_fanout
        decision = decision_fanout(question, options, packet)

        # 3. Confidence route
        routed = confidence_route(decision)
        packet["confidence"] = routed["probability"]
        packet["risk_class"] = risk["risk_class"]

        if routed["route"] == "residual_or_apollo":
            result = self.residual_fn(decision)
            apollo = self.apollo_fn(result)
            v = verify_on_stop(packet, apollo)
            packet["verified"] = v["verified"]
            return {"route": "residual", "result": result, "apollo": apollo, "verify": v, "packet": packet}
        elif routed["route"] == "cascade":
            # Your existing cascade logic here
            return {"route": "cascade", "decision": decision, "packet": packet}
        else:
            return {"route": "escalate", "decision": decision, "packet": packet}
