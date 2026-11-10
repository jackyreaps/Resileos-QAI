"""Harness tool surface.

``ALWAYS_VISIBLE_TOOLS`` is the catalog returned by ``/api/v1/tools``.
``DEMIGOD_TOOLS`` is not in that catalog. A Demi-god is reached by
``search_tool_surface`` or by ``demigod_summon``.
"""
from __future__ import annotations

from typing import Any

from resileos.harness.tools import (
    apollo_success,
    budget_and_stuck_guard,
    confidence_route,
    decision_fanout,
    evidence_attach,
    evidence_attach_raw,
    guide_load,
    residual_consistency,
    risk_classify,
    verification_required,
    verify_on_stop,
)
from resileos.kin.demigods.hierarchy import DemigodError
from resileos.kin.demigods.router import (
    demigod_dismiss,
    demigod_search,
    demigod_summon,
    list_demigods,
)

ALWAYS_VISIBLE_TOOLS = {
    "decision_fanout": decision_fanout,
    "confidence_route": confidence_route,
    "risk_classify": risk_classify,
    "verification_required": verification_required,
    "verify_on_stop": verify_on_stop,
    "budget_and_stuck_guard": budget_and_stuck_guard,
    "guide_load": guide_load,
    "evidence_attach": evidence_attach,
    "evidence_attach_raw": evidence_attach_raw,
    "residual_consistency": residual_consistency,
    "apollo_success": apollo_success,
}

DEMIGOD_TOOLS = {
    "demigod_search": demigod_search,
    "demigod_summon": demigod_summon,
    "demigod_dismiss": demigod_dismiss,
    "list_demigods": list_demigods,
}


def _schema(name: str, fn: Any, *, deferred: bool) -> dict[str, Any]:
    doc = (fn.__doc__ or name).strip().split("\n")[0]
    return {"name": name, "description": doc, "deferred": deferred}


def always_visible_schemas() -> list[dict[str, Any]]:
    """Schemas for the always-visible catalog. Demi-god tools are absent."""
    return [
        _schema(name, fn, deferred=False)
        for name, fn in ALWAYS_VISIBLE_TOOLS.items()
    ]


def search_tool_surface(query: str, limit: int = 8) -> dict[str, Any]:
    """Find harness tools and Demi-gods by name or description.

    A blank query returns no rows. It does not dump either catalog.
    """
    q = (query or "").strip().lower()
    if not q:
        return {"query": query, "results": []}
    results: list[dict[str, Any]] = []
    for name, fn in ALWAYS_VISIBLE_TOOLS.items():
        row = _schema(name, fn, deferred=False)
        if q in name.lower() or q in row["description"].lower():
            results.append(row)
    for name, fn in DEMIGOD_TOOLS.items():
        row = _schema(name, fn, deferred=True)
        row["kind"] = "demigod_tool"
        if q in name.lower() or q in row["description"].lower():
            results.append(row)
    try:
        roster = demigod_search(q, limit=limit)
    except DemigodError:
        roster = {"results": []}
    for hit in roster.get("results") or []:
        results.append(
            {
                "name": hit["name"],
                "description": hit["description"],
                "deferred": True,
                "kind": "demigod",
            }
        )
    cap = limit if isinstance(limit, int) and limit > 0 else 0
    return {"query": query, "results": results[:cap]}


__all__ = [
    "ALWAYS_VISIBLE_TOOLS",
    "DEMIGOD_TOOLS",
    "always_visible_schemas",
    "search_tool_surface",
]
