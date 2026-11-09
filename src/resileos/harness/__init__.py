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
]
