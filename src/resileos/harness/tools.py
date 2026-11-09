"""Harness tools: decision primitives, guards, verification, context.

Expose via leCore / GET /api/v1/tools. All return typed dicts for cascade.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def decision_fanout(
    question: str,
    options: List[str],
    packet: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Jev-style Choice. Returns typed answer + calibrated probability.

    High-conf routes to residual/Apollo; else cascade.
    """
    # Placeholder: replace with your residual query or external Jev call.
    scores = {opt: 0.5 for opt in options}
    if packet and "residual_query" in packet.get("state", {}):
        # wire to your VSA cleanup / bind pass
        pass
    best = max(scores, key=scores.get)
    return {
        "type": "Choice",
        "answer": best,
        "probability": scores[best],
        "options": scores,
        "evidence": [],
    }


def confidence_route(
    result: Dict[str, Any],
    high: float = 0.99,
    mid: float = 0.7,
) -> Dict[str, Any]:
    """Cascade router. high -> residual/Apollo, mid -> cascade, low -> escalate."""
    p = result.get("probability", 0.0)
    if p >= high:
        route = "residual_or_apollo"
    elif p >= mid:
        route = "cascade"
    else:
        route = "escalate_or_abstain"
    return {"route": route, "probability": p, "original": result}


def risk_classify(
    action: str,
    context: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Policy-as-code risk gate (allow/ask/deny).

    Syntax-aware stub; replace with tree-sitter or residual.
    """
    deny_patterns = ["rm -rf", "delete", "drop table", "force push"]
    ask_patterns = ["write", "commit", "deploy", "send"]

    if any(p in action.lower() for p in deny_patterns):
        cls, reason = "deny", "matches hard deny pattern"
    elif any(p in action.lower() for p in ask_patterns):
        cls, reason = "ask", "side-effecting action"
    else:
        cls, reason = "allow", "safe or read-only"
    return {"risk_class": cls, "reason": reason, "action": action}


def verify_on_stop(
    packet: Dict[str, Any],
    apollo_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Outer verification loop. Must pass before closing turn."""
    verified = packet.get("verified", False) or (
        apollo_result and apollo_result.get("success", False)
    )
    if not verified and packet.get("scars"):
        return {
            "verified": False,
            "reason": "unverified residual scars or mutations",
            "action": "force_apollo_or_cleanup",
        }
    return {
        "verified": True,
        "reason": "apollo or residual consistency passed",
    }


def budget_and_stuck_guard(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Budgeted loop + simple stuck detection (hash of recent history)."""
    budget = packet.get("budget_remaining", {})
    if budget.get("steps", 1) <= 0 or budget.get("cost", 1) <= 0:
        return {
            "ok": False,
            "reason": "budget exhausted",
            "action": "stop",
        }
    recent = json.dumps(
        packet.get("history", [])[-3:], sort_keys=True
    )
    h = hashlib.sha256(recent.encode()).hexdigest()[:8]
    if packet.get("last_hash") == h and len(packet.get("history", [])) > 5:
        return {
            "ok": False,
            "reason": "stuck (hash repeat)",
            "action": "compact_or_abort",
        }
    packet["last_hash"] = h
    return {"ok": True, "budget": budget}


def guide_load(
    guides: List[str],
    packet: Dict[str, Any],
) -> Dict[str, Any]:
    """Hierarchical / JIT context (AGENTS.md / CONSTRAINTS.md pattern)."""
    loaded = packet.get("guides_loaded", [])
    for g in guides:
        if g not in loaded:
            loaded.append(g)
    packet["guides_loaded"] = loaded
    return {"loaded": loaded, "packet": packet}


def evidence_attach(
    result: Dict[str, Any],
    source: str,
    packet: Dict[str, Any],
) -> Dict[str, Any]:
    """AgenC-style evidence attachment for every tool/residual update."""
    evidence = packet.get("evidence", [])
    evidence.append({
        "source": source,
        "result": result,
        "turn": packet.get("turn", 0),
    })
    packet["evidence"] = evidence[-50:]
    return {"evidence": packet["evidence"]}


def residual_consistency(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Check the control packet for signs of a broken residual trajectory.

    A packet is consistent when:
      - no unresolved scars are recorded, AND
      - every evidence entry that claims a residual hash has a
        non-empty hash (no placeholder/None entries).

    Returns:
        {"consistent": bool, "reason": str, "scars": list}
    """
    scars = list(packet.get("scars", []) or [])
    evidence = packet.get("evidence", []) or []

    bad_evidence = []
    for e in evidence:
        if e.get("source") != "residual_core":
            continue
        result = e.get("result", {}) or {}
        if result.get("packet_hash") in (None, "", "None"):
            bad_evidence.append(e)

    if scars:
        return {
            "consistent": False,
            "reason": f"{len(scars)} unresolved scars",
            "scars": scars,
        }
    if bad_evidence:
        return {
            "consistent": False,
            "reason": f"{len(bad_evidence)} residual evidence entries lack a hash",
            "scars": scars,
        }
    return {
        "consistent": True,
        "reason": "no scars, residual evidence well-formed",
        "scars": [],
    }


def apollo_success(result: Dict[str, Any]) -> Dict[str, Any]:
    """Outer sensor: did the Apollo / residual pass report success?

    `result` is a dict with at least `status`. Anything other than a
    non-empty status string is treated as failure so verification
    fails closed rather than open.

    Returns:
        {"success": bool, "status": str, "reason": str}
    """
    status = str((result or {}).get("status", "") or "").strip().lower()
    if status in ("ok", "success", "passed", "verified"):
        return {
            "success": True,
            "status": status,
            "reason": "outer sensor reported success",
        }
    return {
        "success": False,
        "status": status or "unknown",
        "reason": f"outer sensor status {status!r} not in success set",
    }
