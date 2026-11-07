"""Optional mouth: prose over retrieved rows.

The mouth is a peripheral. It does not own the record.
If no model is configured, it returns a structured sentence from the rows.
"""
from __future__ import annotations

import os
from typing import Any, Optional


def render_rows(rows: list[dict[str, Any]], question: str = "") -> str:
    """Deterministic mouth when no external model is set."""
    if not rows:
        return "No stored facts for that query."
    parts = []
    for r in rows:
        s = r.get("subject") or r.get("s")
        rel = r.get("relation") or r.get("r")
        o = r.get("obj") or r.get("o") or r.get("value")
        if s and rel and o:
            parts.append(f"{s} {rel} {o}")
    body = "; ".join(parts) if parts else str(rows)
    if question:
        return f"{question} — {body}."
    return body + "."


def mouth_available() -> bool:
    return bool(os.getenv("RESILEOS_MOUTH_URL", "").strip())


def answer_with_mouth(
    rows: list[dict[str, Any]],
    question: str = "",
    *,
    model_fn: Optional[Any] = None,
) -> dict[str, Any]:
    """Return prose. Uses model_fn if given, else deterministic render."""
    if model_fn is not None:
        text = model_fn(rows, question)
        return {"text": text, "backend": "external"}
    return {"text": render_rows(rows, question), "backend": "structured"}
