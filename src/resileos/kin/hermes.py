"""Hermes — context navigator. Layers context under a depth budget."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


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
    ) -> list[Any]:
        b = budget or HermesBudget(max_depth=max_depth, max_items=max_items)
        if not contexts:
            return []
        # Prefer items that look like structured triples/dicts with subject
        scored: list[tuple[int, Any]] = []
        for i, item in enumerate(contexts):
            score = 0
            if isinstance(item, dict):
                if item.get("subject") and item.get("relation"):
                    score += 2
                if item.get("value") is not None or item.get("obj") is not None:
                    score += 1
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                score += 2
            scored.append((score, item))
        scored.sort(key=lambda x: (-x[0],))
        out = [x for _, x in scored[: max(0, int(b.max_items))]]
        b.used = len(out)
        return out

    def handler(parent: Any, subject: str, relation: str, inverse: bool = False) -> None:
        return None

    return navigate, handler
