"""Task loop: goal → store lookups → optional mouth → trace.

The trace is the product. It shows what came from memory and what
came from the mouth, with epistemic labels.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.custom_mouth import answer


def run_task(
    goal: str,
    *,
    ask: Callable[[str, str], Any],
    steps: list[tuple[str, str]],
    mouth_fn: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """Execute a list of (subject, relation) lookups, then render.

    ask(subject, relation) -> row or None
    steps: planned lookups
    """
    trace = []
    rows = []
    for s, r in steps:
        row = ask(s, r)
        entry = {"subject": s, "relation": r, "row": row, "source": "store"}
        if row:
            rows.append(row if isinstance(row, dict) else {"value": row, "subject": s, "relation": r})
            entry["status"] = "HIT"
        else:
            entry["status"] = "MISS"
        trace.append(entry)
    rendered = answer(rows, goal, model_fn=mouth_fn)
    return {
        "goal": goal,
        "trace": trace,
        "answer": rendered,
        "note": "Mouth does not own the record. Empty lookups stay empty.",
    }
