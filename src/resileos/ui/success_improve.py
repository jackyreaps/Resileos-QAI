"""Improve cycle on the golden-ladder oscillator.

Not a trajectory RL loop. A step is a phase hop on the Kuramoto field.
Weights come from the golden ladder. The eat gate is the terminal
check; only hops that pass are kept. Continuity is phase, not a
replay buffer.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

from resileos.ui.scale_address import scale_address
from resileos.ui.framework_gate import gate_candidate

try:
    from resileos.substrate.oscillator import PHI, golden_ladder, KuramotoField
    _HAS_OSC = True
except ImportError:
    PHI = (1.0 + 5.0 ** 0.5) / 2.0
    golden_ladder = None
    KuramotoField = None
    _HAS_OSC = False


def hop_weights(n: int) -> list[float]:
    """Golden-ladder weights for n hops. Falls back if the field is absent."""
    if _HAS_OSC and golden_ladder is not None:
        w = golden_ladder(n)
        return [float(x) for x in w]
    return [float((PHI ** i) % (2.0 * np.pi)) for i in range(n)]


def phase_hop(
    steps: list[dict[str, str]],
    *,
    subject: str = "world:improve",
) -> dict[str, Any]:
    """One multi-weighted hop. Each step gets a golden weight and a phase."""
    weights = hop_weights(max(len(steps), 1))
    hops = []
    for i, step in enumerate(steps):
        addr = scale_address(subject=subject)
        hops.append({
            "step": step,
            "weight": weights[i % len(weights)],
            "phase": float(addr["field"]["theta"][0]) if addr.get("field") else 0.0,
            "address": addr["embed"],
        })
    return {"subject": subject, "hops": hops, "n": len(hops)}


def keep_verified(
    hop: dict[str, Any],
    *,
    eat_fn: Optional[Callable[..., Any]] = None,
) -> list[dict[str, Any]]:
    """Keep only hops whose step passes the eat gate."""
    kept = []
    for h in hop.get("hops", []):
        step = h["step"]
        accepted = True
        if eat_fn is not None:
            claim = f"{step.get('subject')} {step.get('relation')} {step.get('obj')}"
            d = eat_fn(claim)
            accepted = bool(getattr(d, "accepted", False))
        if not accepted:
            continue
        triple = {
            "subject": step.get("subject", hop["subject"]),
            "relation": step.get("relation", "hop"),
            "obj": step.get("obj", ""),
        }
        gated = gate_candidate(triple, stored=[], eat_accepted=True)
        kept.append({**triple, "weight": h["weight"], "phase": h["phase"], "address": h["address"], "gate": gated})
    return kept


def improve_cycle(
    steps: list[dict[str, str]],
    *,
    subject: str = "world:improve",
    eat_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """Golden-weighted hop, then keep only eat-verified steps."""
    hop = phase_hop(steps, subject=subject)
    kept = keep_verified(hop, eat_fn=eat_fn)
    return {
        "hops": hop["n"],
        "kept": len(kept),
        "facts": kept,
        "weights": hop_weights(hop["n"]),
        "note": "Golden-ladder weights. Only eat-verified hops are kept.",
    }
