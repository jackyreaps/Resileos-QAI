"""Athena kin: judgment across modalities and meta frames.

Reads perception addresses and a Psyche frame stack. Returns one gated
reading. Human Medium frames are consumed, not reimplemented.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.framework_gate import gate_candidate


def judge(
    perceptions: list[dict[str, Any]],
    *,
    subject: str = "world:reading",
    eat_fn: Optional[Callable[..., Any]] = None,
    frames: Optional[list[dict[str, Any]]] = None,
    drives: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """One reading from modalities and optional finished frames."""
    if not perceptions and not frames:
        return {"ok": False, "note": "nothing to judge", "gate": {"frame": "abstained"}}
    parts = []
    for p in perceptions:
        addr = p.get("address") or {}
        parts.append(f"{p.get('subject','mod')}:{addr.get('residual_bin','unknown')}")
    frame_label = ""
    if frames:
        top = frames[-1]
        frame_label = str(top.get("label", ""))
        if frame_label:
            parts.insert(0, f"frame:{frame_label}")
    if drives:
        hot = [k for k, v in drives.items() if float(v) > 0.5]
        if hot:
            parts.append("drives:" + ",".join(hot))
    reading = " | ".join(parts) if parts else "empty"
    triple = {"subject": subject, "relation": "judgment", "obj": reading[:180]}
    accepted = False
    if eat_fn is not None:
        d = eat_fn(f"{triple['subject']} {triple['relation']} {triple['obj']}")
        accepted = bool(getattr(d, "accepted", False))
    gated = gate_candidate(triple, stored=[], eat_accepted=accepted)
    return {
        "ok": gated.get("frame") != "abstained",
        "reading": reading,
        "gate": gated,
        "modalities": len(perceptions),
        "frame": frame_label,
        "depth": int(frames[-1].get("depth", 0)) if frames else 0,
    }


def load_frame(label: str, *, depth: int = 1, parent: str | None = None) -> dict[str, Any]:
    """Adapter. A finished Human Medium frame becomes an address Psyche can hold."""
    return {"label": label.strip(), "depth": int(depth), "parent": parent}
