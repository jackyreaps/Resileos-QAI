"""Perception route helpers.

Image or caption in → candidate triples → eat filter → report.
Does not assert facts unless the caller sets commit=True and eat accepts.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.perception import triples_from_caption


def perceive(
    caption: str,
    *,
    subject: str = "image",
    eat_fn: Optional[Callable[..., Any]] = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Turn a caption into candidates and optionally run them through eat.

    eat_fn: callable(claim) -> decision with .accepted and .to_dict()
    commit: if True and eat accepts, the caller is responsible for learn().
    """
    cands = triples_from_caption(caption, subject=subject)
    results = []
    for c in cands:
        claim = f"{c['subject']} {c['relation']} {c['obj']}"
        row: dict[str, Any] = {"triple": c, "claim": claim}
        if eat_fn is not None:
            decision = eat_fn(claim)
            row["eat"] = decision.to_dict() if hasattr(decision, "to_dict") else decision
            row["accepted"] = bool(getattr(decision, "accepted", False))
        else:
            row["accepted"] = False
            row["eat"] = {"note": "no eat filter supplied"}
        results.append(row)
    return {
        "caption": caption,
        "subject": subject,
        "candidates": results,
        "committed": False,
        "note": "Candidates are not facts until eat accepts and learn is called.",
    }
