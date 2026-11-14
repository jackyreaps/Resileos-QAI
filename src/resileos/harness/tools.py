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
from resileos.run_trace import traced as _traced


def _residual_rows(packet: Optional[Dict]) -> list:
    """Rows already on the packet. Fan-out does not invent any."""
    if not isinstance(packet, dict):
        return []
    state = packet.get("state")
    if not isinstance(state, dict):
        return []
    rows: list = []
    for key in ("rows", "residual_rows"):
        value = state.get(key)
        if isinstance(value, list):
            rows.extend(value)
    query = state.get("residual_query")
    if isinstance(query, dict) and isinstance(query.get("rows"), list):
        rows.extend(query["rows"])
    elif isinstance(query, str) and query.strip():
        rows.append(query)
    return rows


def _row_text(row: Any) -> str:
    if isinstance(row, dict):
        parts = [row.get("subject"), row.get("relation"), row.get("obj"), row.get("value")]
        return " ".join(str(part) for part in parts if part)
    return str(row)


def decision_fanout(
    question: str,
    options: List[str],
    packet: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Choose an option only when it overlaps residual rows.

    No residual support scores 0 and leaves the answer empty. That is an
    abstain, not a calibrated guess.
    """
    del question
    if not options:
        return {
            "type": "Choice",
            "answer": "",
            "probability": 0.0,
            "options": {},
            "evidence": [],
        }
    blob_tokens: set[str] = set()
    pieces: list[str] = []
    for row in _residual_rows(packet):
        text = _row_text(row).strip().lower()
        if not text:
            continue
        pieces.append(text)
        blob_tokens.update(part for part in text.replace("_", " ").split() if part)
    joined = " ".join(pieces)
    scores: Dict[str, float] = {}
    evidence: list = []
    for opt in options:
        opt_text = str(opt).strip().lower()
        opt_tokens = [part for part in opt_text.replace("_", " ").split() if part]
        if opt_text and opt_text in joined:
            score = 0.99
        elif opt_tokens and blob_tokens:
            shared = sum(1 for token in opt_tokens if token in blob_tokens)
            if shared == len(opt_tokens):
                score = 0.8
            elif shared:
                score = 0.75
            else:
                score = 0.0
        else:
            score = 0.0
        scores[opt] = score
        if score > 0:
            evidence.append({"option": str(opt), "score": score, "source": "residual_rows"})
    best = max(options, key=lambda opt: scores[opt])
    if scores[best] <= 0:
        answer = ""
        probability = 0.0
    else:
        answer = best
        probability = scores[best]
    return {
        "type": "Choice",
        "answer": answer,
        "probability": probability,
        "options": scores,
        "evidence": evidence,
    }


@_traced("route", lambda r: {"route": r.get("route"), "probability": r.get("probability")})
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


@_traced("risk", lambda r: {"risk_class": r.get("risk_class"), "reason": r.get("reason")})
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


# evidence_attach keeps this many entries. Hephaestus treats it as a hard cap.
EVIDENCE_CAP = 50

# Persona text injected with a guide id. Shared by guide_load and Demi-gods.
GUIDE_BODY_CAP = 4000


@_traced("budget", lambda r: {"ok": r.get("ok"), "reason": r.get("reason")})
def budget_and_stuck_guard(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Budgeted loop + simple stuck detection.

    Counts steps and cost, and, when the packet carries them, wall time
    (``seconds``) and memory (``memory_mb``): any of them at or below
    zero stops the loop.
    """
    budget = packet.get("budget_remaining", {})
    if any(budget.get(key, 1) <= 0 for key in ("steps", "cost", "seconds", "memory_mb")):
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


def _guide_containers(packet: Any) -> tuple[list, dict]:
    """Return the caller's live guides list and body dict.

    Accepts a ControlPacket or a dict the caller keeps. Lists and dicts
    are mutated in place. ControlPacket.to_dict() shares those objects,
    so an in-place edit also updates the packet the dict was taken from.
    """
    from resileos.harness.packet import ControlPacket

    if isinstance(packet, ControlPacket):
        if not isinstance(packet.guide_bodies, dict):
            packet.guide_bodies = {}
        if not isinstance(packet.guides_loaded, list):
            packet.guides_loaded = list(packet.guides_loaded or [])
        return packet.guides_loaded, packet.guide_bodies
    if isinstance(packet, dict):
        loaded = packet.get("guides_loaded")
        if not isinstance(loaded, list):
            loaded = list(loaded or [])
            packet["guides_loaded"] = loaded
        stored = packet.get("guide_bodies")
        if not isinstance(stored, dict):
            stored = {}
            packet["guide_bodies"] = stored
        return loaded, stored
    raise TypeError("guide_load packet must be a ControlPacket or a dict")


def guide_load(
    guides: list[str],
    packet: Any,
    *,
    bodies: dict[str, str] | None = None,
    body_cap: int = GUIDE_BODY_CAP,
) -> dict[str, Any]:
    """Hierarchical / JIT context (AGENTS.md / CONSTRAINTS.md pattern).

    Filenames (or guide ids) are recorded on ``guides_loaded``. When
    ``bodies`` is provided, each body is stored under ``guide_bodies``,
    truncated to ``body_cap`` characters. The cap is the single injection
    point for Demi-god persona text and any other bounded guide.
    """
    if body_cap < 0:
        raise ValueError("body_cap must be >= 0")
    loaded, stored = _guide_containers(packet)
    for g in guides:
        if g not in loaded:
            loaded.append(g)
    if bodies:
        for key, body in bodies.items():
            text = body if isinstance(body, str) else str(body)
            stored[str(key)] = text[:body_cap]
    return {"loaded": loaded, "bodies": dict(stored), "packet": packet}


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
    packet["evidence"] = evidence[-EVIDENCE_CAP:]
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


@_traced("consistency", lambda r: {"ok": r.get("consistent"), "issues": len(r.get("scars") or [])})
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
    "GUIDE_BODY_CAP",
    "EVIDENCE_CAP",
    "guide_load",
    "evidence_attach",
    "evidence_attach_raw",
    "residual_consistency",
    "apollo_success",
]
