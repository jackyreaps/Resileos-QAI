"""Aggregate counters from seed events."""
from __future__ import annotations

from typing import Any

from resileos.seed.log import iter_events
from resileos.seed.types import SeedEvent


def metrics_from_events(events: list[SeedEvent]) -> dict[str, Any]:
    teaches = hits = misses = assets = sessions = persona = mouth = 0
    for ev in events:
        t = ev.event_type
        if t == "fact_learned":
            teaches += 1
        elif t == "query_hit":
            hits += 1
        elif t == "query_miss":
            misses += 1
        elif t == "asset_registered":
            assets += 1
        elif t == "session_start":
            sessions += 1
        elif t == "persona_set":
            persona += 1
        elif t == "mouth_used":
            mouth += 1
    total_q = hits + misses
    return {
        "teaches": teaches,
        "hits": hits,
        "misses": misses,
        "assets": assets,
        "sessions": sessions,
        "persona_sets": persona,
        "mouth_used": mouth,
        "hit_rate": (hits / total_q) if total_q else 0.0,
        "queries": total_q,
    }


def metrics_for(user_id: str, *, limit: int = 2000) -> dict[str, Any]:
    return metrics_from_events(iter_events(user_id, limit=limit))
