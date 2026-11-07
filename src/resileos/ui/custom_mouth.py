"""Custom mouth: language as a gate, not the record.

Aligned with Human Medium Part V: language modulates between global
(store) and local (utterance). It does not invent facts.

Modes:
  structured — deterministic sentence from rows
  external   — optional model, constrained to the rows
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

from resileos.ui.scale_address import scale_address


def epistemic_label(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "ABSTAINED"
    return "GROUNDED"


def render_structured(rows: list[dict[str, Any]], question: str = "") -> str:
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
    prefix = f"{question} — " if question else ""
    return prefix + body + "."


def mouth_prompt(rows: list[dict[str, Any]], question: str) -> str:
    """Prompt for an external model. Constrains it to the rows."""
    facts = "\n".join(
        f"- {r.get('subject')} {r.get('relation')} {r.get('obj') or r.get('value')}"
        for r in rows
        if r.get("subject")
    )
    return (
        "Answer only from the facts below. If the answer is not in the facts, "
        "reply exactly UNKNOWN. Do not add information.\n\n"
        f"Facts:\n{facts}\n\nQuestion: {question}"
    )


def answer(
    rows: list[dict[str, Any]],
    question: str = "",
    *,
    model_fn: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """Return an answer with epistemic status.

    model_fn receives the constrained prompt and returns text.
    """
    label = epistemic_label(rows)
    if model_fn is not None and rows:
        text = model_fn(mouth_prompt(rows, question))
        backend = "external"
    else:
        text = render_structured(rows, question)
        backend = "structured"
    addr = scale_address(subject="mouth")
    return {
        "text": text,
        "backend": backend,
        "epistemic": label,
        "row_count": len(rows),
        "scale": {"address": addr["embed"], "gate": addr["gate"]},
    }


def mouth_configured() -> bool:
    return bool(os.getenv("RESILEOS_MOUTH_URL", "").strip())
