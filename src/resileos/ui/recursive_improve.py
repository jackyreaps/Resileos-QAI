"""Recursive self-improvement on a hub.

Inspired by alternating rewrite and refine phases with strict verification.
Uses the eat gate as the terminal verifier and the scale address for
trajectory storage. Does not retrain weights; it improves the hub state.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.scale_address import scale_address
from resileos.ui.framework_gate import gate_candidate


def rewrite_trajectory(
    hub_facts: list[dict[str, str]],
    *,
    subject: str = "world:improve",
) -> list[dict[str, Any]]:
    """RSR-style: take successful facts and produce refined candidates."""
    refined = []
    for fact in hub_facts:
        addr = scale_address(subject=subject)
        candidate = {
            "subject": fact.get("subject", subject),
            "relation": fact.get("relation", "refined"),
            "obj": fact.get("obj", ""),
            "address": addr["embed"],
        }
        refined.append(candidate)
    return refined


def refine_with_verifier(
    candidates: list[dict[str, Any]],
    *,
    eat_fn: Optional[Callable[..., Any]] = None,
) -> list[dict[str, Any]]:
    """RPR-style: keep only those that pass the eat gate."""
    kept = []
    for c in candidates:
        accepted = False
        if eat_fn is not None:
            claim = f"{c['subject']} {c['relation']} {c['obj']}"
            d = eat_fn(claim)
            accepted = bool(getattr(d, "accepted", False))
        gated = gate_candidate(c, stored=[], eat_accepted=accepted)
        if gated["frame"] != "abstained":
            kept.append({**c, "gate": gated})
    return kept


def recursive_step(
    hub_facts: list[dict[str, str]],
    *,
    subject: str = "world:improve",
    eat_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """One full RSR + RPR step on the hub."""
    rewritten = rewrite_trajectory(hub_facts, subject=subject)
    refined = refine_with_verifier(rewritten, eat_fn=eat_fn)
    return {
        "rewritten": len(rewritten),
        "kept": len(refined),
        "facts": refined,
        "note": "Strict verifier kept only non-abstained candidates.",
    }
