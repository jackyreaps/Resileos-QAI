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


def epistemic_label(rows: list[dict[str, Any]], *, status: str = "") -> str:
    label = (status or "").upper()
    if label in {"ABSTAINED", "CONFLICT", "CANDIDATE"}:
        return label
    if not rows:
        return "ABSTAINED"
    if _conflicting(rows):
        return "CONFLICT"
    return "GROUNDED"


def _fields(row: dict[str, Any]) -> tuple[str, str, str]:
    subject = str(row.get("subject") or row.get("s") or "")
    relation = str(row.get("relation") or row.get("r") or "")
    obj = row.get("obj")
    if obj is None:
        obj = row.get("o")
    if obj is None:
        obj = row.get("value")
    return subject, relation, "" if obj is None else str(obj)


def _window(row: dict[str, Any]) -> str:
    start = row.get("valid_from")
    end = row.get("valid_to")
    if start in (None, "") and end in (None, ""):
        return ""
    left = str(start) if start not in (None, "") else "open start"
    right = str(end) if end not in (None, "") else "open end"
    return f"from {left} until {right}"


def _conflicting(rows: list[dict[str, Any]]) -> bool:
    grouped: dict[tuple[str, str], set[str]] = {}
    windows = False
    for row in rows:
        subject, relation, obj = _fields(row)
        if not (subject and relation and obj):
            continue
        grouped.setdefault((subject, relation), set()).add(obj)
        if _window(row):
            windows = True
    if not windows:
        return False
    return any(len(objs) > 1 for objs in grouped.values())


def phrase_candidate(candidate: Any, evidence: list[dict[str, Any]] | None = None) -> str:
    """Hypothesis line. A candidate is not a stored fact."""
    del evidence
    name = str(candidate).strip() if candidate not in (None, "") else "none"
    return f"I don't have that on record; closest match is {name}, unverified."


def explain_records(
    rows: list[dict[str, Any]],
    *,
    status: str = "",
    reason: str = "",
) -> str | None:
    """Say why a turn abstains or conflicts, from the rows in hand.

    No model call. An empty row list keeps the stored-facts sentence.
    """
    label = (status or "").upper()
    if not rows:
        base = "No stored facts for that query."
        detail = (reason or "").strip()
        if label == "ABSTAINED" and detail:
            return f"{base} {detail}"
        if label == "CANDIDATE":
            return phrase_candidate(None)
        return base if not detail else f"{base} {detail}"
    if label == "CANDIDATE":
        return phrase_candidate(reason or None)
    if label != "CONFLICT" and not _conflicting(rows):
        return None
    parts = []
    for row in rows:
        subject, relation, obj = _fields(row)
        if not (subject and relation and obj):
            continue
        window = _window(row)
        parts.append(f"{subject} {relation} {obj}" + (f" ({window})" if window else ""))
    if not parts:
        return None
    return "These records disagree: " + "; ".join(parts) + ". I will not pick one."


def render_structured(
    rows: list[dict[str, Any]],
    question: str = "",
    *,
    status: str = "",
    reason: str = "",
) -> str:
    explained = explain_records(rows, status=status, reason=reason)
    if explained is not None and (
        not rows or (status or "").upper() in {"ABSTAINED", "CONFLICT", "CANDIDATE"} or _conflicting(rows)
    ):
        if question and rows:
            return f"{question} — {explained}"
        return explained
    if not rows:
        return "No stored facts for that query."
    parts = []
    for row in rows:
        subject, relation, obj = _fields(row)
        if subject and relation and obj:
            parts.append(f"{subject} {relation} {obj}")
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
    status: str = "",
    reason: str = "",
    candidate: Any = None,
) -> dict[str, Any]:
    """Return an answer with epistemic status.

    model_fn receives the constrained prompt and returns text.
    Conflict, abstain, and candidate lines stay on the structured
    mouth. They do not call a model.
    """
    label = epistemic_label(rows, status=status)
    structured_only = label in {"ABSTAINED", "CONFLICT", "CANDIDATE"}
    if label == "CANDIDATE":
        text = phrase_candidate(candidate if candidate not in (None, "") else reason)
        backend = "structured"
    elif model_fn is not None and rows and not structured_only:
        text = model_fn(mouth_prompt(rows, question))
        backend = "external"
    else:
        text = render_structured(rows, question, status=label if structured_only else status, reason=reason)
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
