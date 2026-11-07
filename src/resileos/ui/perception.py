"""Perception helpers for the portable UI.

Turns an image caption or description into candidate triples
and returns them for the eat filter. Does not assert facts.
"""
from __future__ import annotations

from typing import Any


def triples_from_caption(caption: str, subject: str = "image") -> list[dict[str, str]]:
    """Naive extraction: 'a red car on a road' -> candidate triples.

    This is a pre-model bridge. A real encoder replaces this later.
    Candidates are not facts until the eat filter accepts them.
    """
    text = (caption or "").strip()
    if not text:
        return []
    # very small rule set for demo; not a vision model
    triples: list[dict[str, str]] = []
    lower = text.lower()
    if "red" in lower:
        triples.append({"subject": subject, "relation": "has_color", "obj": "red"})
    if "car" in lower or "vehicle" in lower:
        triples.append({"subject": subject, "relation": "depicts", "obj": "vehicle"})
    if "road" in lower or "street" in lower:
        triples.append({"subject": subject, "relation": "located_on", "obj": "road"})
    if not triples:
        triples.append({"subject": subject, "relation": "caption", "obj": text[:80]})
    return triples


def perception_payload(caption: str, subject: str = "image") -> dict[str, Any]:
    """Payload the UI can send to /api/v1/eat for each candidate."""
    cands = triples_from_caption(caption, subject)
    return {
        "candidates": cands,
        "note": "Candidates only. Run through eat before learn.",
    }
