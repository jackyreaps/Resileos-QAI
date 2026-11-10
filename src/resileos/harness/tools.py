"""Harness tools: decision primitives, guards, verification, context.

Expose via leCore / GET /api/v1/tools. All return typed dicts for cascade.

Verification contract (added 2026-11-09):
    - A turn is not verified because it produced output. It is verified
      because a probe ran and produced raw evidence.
    - Zero matched cases is not evidence. verify_on_stop rejects an
      evidence entry whose result.matched == 0 when require_evidence=True.
    - Summaries are not evidence. evidence_attach_raw rejects results
      containing only summary/note/status keys.
    - Unknown action types default to requiring verification (fail closed).
    - Fixes a fail-open bug in verify_on_stop: a failed apollo with no
      scars previously returned verified=True. The require_evidence=True
      path now returns verified=False. Callers not passing require_evidence
      keep the old (buggy) behaviour for backwards compatibility.
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
    """Jev-style Choice. Returns typed answer + calibrated probability."""
    scores = {opt: 0.5 for opt in options}
    if packet and "residual_query" in packet.get("state", {}):
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
    """Policy-as-code risk gate (allow/ask/deny)."""
    deny_patterns = ["rm -rf", "delete", "drop table", "force push"]
    ask_patterns = ["write", "commit", "deploy", "send"]

    if any(p in action.lower() for p in deny_patterns):
        cls, reason = "deny", "matches hard deny pattern"
    elif any(p in action.lower() for p in ask_patterns):
        cls, reason = "ask", "side-effecting action"
    else:
        cls, reason = "allow", "safe or read-only"
    return {"risk_class": cls, "reason": reason, "action": action}


_VERIFICATION_REQUIRED = {
    "learn", "learn_batch", "save", "train_substrate",
    "kin_cycle", "eat", "council_query", "workbench",
    "deploy", "migrate",
}
_VERIFICATION_OPTIONAL = {
    "query", "chain", "sparql", "answer", "tools", "stats",
    "ready", "substrate_stats", "lecore_route",
}


def verification_required(action_type: str) -> Dict[str, Any]:
    """Classify whether an action type demands verification evidence."""
    at = (action_type or "").strip().lower()
    if at in _VERIFICATION_OPTIONAL:
        return {
            "action_type": at,
            "requires_verification": False,
            "reason": "read-only or lookup",
        }
    if at in _VERIFICATION_REQUIRED:
        return {
            "action_type": at,
            "requires_verification": True,
            "reason": "mutation or cycle; evidence required before close",
        }
    return {
        "action_type": at,
        "requires_verification": True,
        "reason": "unknown action type; fail closed",
    }


def verify_on_stop(
    packet: Dict[str, Any],
    apollo_result: Optional[Dict] = None,
    *,
    require_evidence: bool = False,
) -> Dict[str, Any]:
    """Outer verification loop. Must pass before closing turn.

    Fail closed. Apollo success False and an unverified packet return
    verified=False on the default path and on require_evidence=True.
    Scars also fail closed.
    """
    packet_verified = bool(packet.get("verified", False))
    apollo_ok = bool(apollo_result and apollo_result.get("success", False))
    scars = packet.get("scars", []) or []

    if scars:
        return {
            "verified": False,
            "reason": "unverified residual scars or mutations",
            "action": "force_apollo_or_cleanup",
        }

    if not require_evidence:
        verified = packet_verified or apollo_ok
        return {
            "verified": verified,
            "reason": (
                "apollo or residual consistency passed"
                if verified
                else "not verified"
            ),
        }

    # Strict path
    if not (packet_verified or apollo_ok):
        return {
            "verified": False,
            "reason": "apollo did not report success",
            "action": "force_apollo",
        }

    evidence = packet.get("evidence", []) or []
    real = [
        e for e in evidence
        if e.get("source") not in (None, "", "summary", "note")
    ]
    if not real:
        return {
            "verified": False,
            "reason": "no evidence attached",
            "action": "run_probe_and_attach",
        }
    for e in real:
        result = e.get("result", {}) or {}
        if "matched" in result and int(result["matched"]) == 0:
            return {
                "verified": False,
                "reason": "zero matched cases in evidence",
                "action": "widen_filter_or_abstain",
            }

    return {
        "verified": True,
        "reason": "apollo passed with evidence",
    }


def budget_and_stuck_guard(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Budgeted loop + simple stuck detection."""
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
    """AgenC-style evidence attachment."""
    evidence = packet.get("evidence", [])
    evidence.append({
        "source": source,
        "result": result,
        "turn": packet.get("turn", 0),
    })
    packet["evidence"] = evidence[-50:]
    return {"evidence": packet["evidence"]}


def evidence_attach_raw(
    result: Dict[str, Any],
    source: str,
    packet: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach raw evidence. Rejects summary-only payloads."""
    if not isinstance(result, dict):
        raise TypeError("result must be a dict")
    if not result:
        raise ValueError("empty result is not evidence")
    keys = set(result.keys())
    if keys <= {"summary", "note", "status"}:
        raise ValueError(
            f"result contains only {sorted(keys)}; "
            f"attach the raw probe output, not a summary"
        )
    return evidence_attach(result, source, packet)


def residual_consistency(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Check the control packet for signs of a broken residual trajectory."""
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
    """Outer sensor: did the Apollo / residual pass report success?"""
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


__all__ = [
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
