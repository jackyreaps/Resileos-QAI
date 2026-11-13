"""Hermes — context navigator. Layers context under a depth budget."""
from __future__ import annotations

from resileos.ui.recursive_improve import recursive_step

from resileos.ui.attach_scale import attach_scale

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# Hephaestus caps the navigator. Metis may widen inside these, not past them.
HEPHAESTUS_MAX_DEPTH = 4
HEPHAESTUS_MAX_ITEMS = 16


@dataclass
class HermesBudget:
    max_depth: int = 2
    max_items: int = 8
    used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_hermes_navigator(*, max_depth: int = 2, max_items: int = 8):
    """
    navigate(contexts, budget) -> filtered list

    Does not invent context. Only truncates / ranks provided items.
    """

    def navigate(
        contexts: list[Any],
        budget: Optional[HermesBudget] = None,
        *,
        neighbours: Optional[list[str]] = None,
    ) -> list[Any]:
        b = budget or HermesBudget(max_depth=max_depth, max_items=max_items)
        if not contexts:
            return []
        neighbour_set = {str(token).lower() for token in (neighbours or []) if str(token).strip()}
        # Prefer items that look like structured triples/dicts with subject.
        # Neighbour tokens from Dionysus can raise a provided item. They
        # do not add a triple that was not already in `contexts`.
        scored: list[tuple[int, int, Any]] = []
        for i, item in enumerate(contexts):
            score = 0
            if isinstance(item, dict):
                if item.get("subject") and item.get("relation"):
                    score += 2
                if item.get("value") is not None or item.get("obj") is not None:
                    score += 1
                text = " ".join(
                    str(item.get(key) or "")
                    for key in ("content", "subject", "relation", "obj", "value")
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                score += 2
                text = " ".join(str(part) for part in item)
            else:
                text = str(item)
            if neighbour_set:
                tokens = {part.lower() for part in text.replace("_", " ").split()}
                if tokens & neighbour_set:
                    score += 1
            scored.append((score, i, item))
        scored.sort(key=lambda row: (-row[0], row[1]))
        out = [item for _, _, item in scored[: max(0, int(b.max_items))]]
        b.used = len(out)
        return out

    def handler(parent: Any, subject: str, relation: str, inverse: bool = False) -> None:
        return None

    return navigate, handler

def hermes_recursive(facts: list, subject: str = "world:kin") -> dict:
    """Run one recursive improve step from this kin."""
    return recursive_step(facts, subject=subject)
