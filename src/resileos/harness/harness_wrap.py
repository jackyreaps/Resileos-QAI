"""Harness wrapping for individual kin handlers.

For kin that are read-only or observation-class, this attaches a
ControlPacket, runs the guard, and returns a harness summary alongside
the handler's result. For mutating kin, use SeparatedCycle instead.
"""
from __future__ import annotations

from uuid import uuid4
from typing import Any, Callable

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    apollo_success,
    budget_and_stuck_guard,
    evidence_attach_raw,
    guide_load,
    verification_required,
    verify_on_stop,
)

_GUIDES = ["docs/harness/CONSTRAINTS.md", "docs/harness/AGENTS.md"]


def harness_wrap(
    handler: Callable[..., Any],
    action_type: str,
    *,
    capture_evidence: bool = True,
) -> Callable[..., dict]:
    def wrapped(*args: Any, **kwargs: Any) -> dict:
        packet = ControlPacket(id=f"{action_type}-{uuid4().hex[:8]}")
        guide_load(_GUIDES, packet.to_dict())

        guard = budget_and_stuck_guard(packet.to_dict())
        if not guard["ok"]:
            return {
                "error": "guard_fail",
                "reason": guard["reason"],
                "harness": {"verified": False},
            }

        result = handler(*args, **kwargs)

        if capture_evidence and isinstance(result, dict) and result:
            try:
                evidence_attach_raw(result, action_type, packet.to_dict())
            except (ValueError, TypeError):
                pass

        verification = verification_required(action_type)
        v = verify_on_stop(
            packet.to_dict(),
            apollo_success(result if isinstance(result, dict) else {}),
            require_evidence=verification["requires_verification"],
        )
        return {"result": result, "harness": v}

    return wrapped
