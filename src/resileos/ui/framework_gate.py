"""Epistemic frame for a candidate triple.

exact          stored match
reconstructed  eat accepted, not yet in the store snapshot
abstained      not accepted and not stored
"""
from __future__ import annotations

from typing import Any, Optional


def residual_debt(triple: dict[str, str], stored: Optional[list[dict[str, str]]] = None) -> int:
    stored = stored or []
    key = (triple.get("subject"), triple.get("relation"), triple.get("obj"))
    for row in stored:
        if (row.get("subject"), row.get("relation"), row.get("obj")) == key:
            return 0
    return 1


def classify(debt: int, eat_accepted: bool) -> str:
    if debt == 0:
        return "exact"
    if eat_accepted:
        return "reconstructed"
    return "abstained"


def gate_candidate(
    triple: dict[str, str],
    *,
    stored: Optional[list[dict[str, str]]] = None,
    eat_accepted: bool = False,
) -> dict[str, Any]:
    debt = residual_debt(triple, stored)
    return {
        "triple": triple,
        "debt": debt,
        "frame": classify(debt, eat_accepted),
    }
