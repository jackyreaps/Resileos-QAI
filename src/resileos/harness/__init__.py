"""Resileos Harness layer: decision routing, guards, verification, and tool surfaces.

Integrates AgenC-style risk/session, Jev-style cascade, and Harness
Engineering patterns.
"""
from .packet import ControlPacket
from .tools import (
    apollo_success,
    budget_and_stuck_guard,
    confidence_route,
    decision_fanout,
    evidence_attach,
    evidence_attach_raw,
    guide_load,
    residual_consistency,
    risk_classify,
    verification_required,
    verify_on_stop,
)
from .cascade import CascadeRouter


def __getattr__(name: str):
    """Demi-god surface and the maker/blind cycle, on demand.

    Importing them at module load would cycle through the Demi-god
    package, which itself imports harness.tools.
    """
    if name in {
        "ALWAYS_VISIBLE_TOOLS",
        "DEMIGOD_TOOLS",
        "always_visible_schemas",
        "search_tool_surface",
    }:
        from resileos.harness import surface as surface

        return getattr(surface, name)
    if name == "maker_blind_verifier_cycle":
        from resileos.harness.separated import maker_blind_verifier_cycle

        return maker_blind_verifier_cycle
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ControlPacket",
    "CascadeRouter",
    "decision_fanout",
    "confidence_route",
    "risk_classify",
    "verification_required",
    "verify_on_stop",
    "budget_and_stuck_guard",
    "guide_load",
    "evidence_attach",
    "evidence_attach_raw",
    "residual_consistency",
    "apollo_success",
    "ALWAYS_VISIBLE_TOOLS",
    "DEMIGOD_TOOLS",
    "always_visible_schemas",
    "search_tool_surface",
    "maker_blind_verifier_cycle",
]
