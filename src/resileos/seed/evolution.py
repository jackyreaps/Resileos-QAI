"""Record seed events and build bootstrap payloads."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from resileos.seed.log import append_event, iter_events
from resileos.seed.metrics import metrics_for
from resileos.seed.types import EVENT_TYPES, BootstrapPayload, SeedEvent


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uid(user_id: str) -> str:
    u = "".join(c for c in (user_id or "").strip().lower() if c.isalnum() or c in "_-")
    return (u or "anon")[:64]


def record_event(
    user_id: str,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
) -> SeedEvent:
    """Append a seed event. Unknown types are still stored (forward compatible)."""
    ev = SeedEvent(
        ts=_now(),
        user_id=_uid(user_id),
        event_type=event_type if event_type else "unknown",
        payload=dict(payload or {}),
    )
    append_event(ev)
    return ev


def record_learn(
    user_id: str,
    subject: str,
    relation: str,
    obj: str,
) -> SeedEvent:
    return record_event(
        user_id,
        "fact_learned",
        {
            "subject": str(subject)[:200],
            "relation": str(relation)[:120],
            "obj": str(obj)[:300],
        },
    )


def record_query_result(
    user_id: str,
    subject: str,
    relation: str,
    hit: bool,
) -> SeedEvent:
    return record_event(
        user_id,
        "query_hit" if hit else "query_miss",
        {
            "subject": str(subject)[:200],
            "relation": str(relation)[:120],
        },
    )


def record_asset(
    user_id: str,
    asset_id: str,
    kind: str,
    path: str,
    title: str = "",
) -> SeedEvent:
    return record_event(
        user_id,
        "asset_registered",
        {
            "asset_id": str(asset_id)[:80],
            "kind": str(kind)[:40],
            "path": str(path)[:500],
            "title": str(title)[:200],
        },
    )


def _profile_from_optional(user_id: str) -> dict[str, Any]:
    """Best-effort load of user_profile if package present."""
    try:
        from resileos.answer.user_profile import load_profile  # type: ignore
    except Exception:
        return {
            "display_name": "",
            "persona": "honest",
            "interests": [],
            "turn_count": 0,
        }

    def post(path: str, payload: dict) -> tuple[int, Any]:
        # No HTTP in unit tests — profile load will no-op without store.
        return 503, {}

    try:
        prof = load_profile(user_id, post)
        return {
            "display_name": prof.display_name,
            "persona": prof.persona,
            "interests": list(prof.interests),
            "turn_count": int(prof.turn_count),
        }
    except Exception:
        return {
            "display_name": "",
            "persona": "honest",
            "interests": [],
            "turn_count": 0,
        }


def _recent_assets(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for ev in reversed(iter_events(user_id, limit=500)):
        if ev.event_type != "asset_registered":
            continue
        assets.append(dict(ev.payload))
        if len(assets) >= limit:
            break
    return assets


def bootstrap(user_id: str, *, session: bool = True) -> BootstrapPayload:
    """Load profile hints, metrics, recent assets; optional session_start event."""
    uid = _uid(user_id)
    if session:
        record_event(uid, "session_start", {})
    prof = _profile_from_optional(uid)
    # Persona from last persona_set event overrides empty profile
    for ev in reversed(iter_events(uid, limit=200)):
        if ev.event_type == "persona_set" and ev.payload.get("persona"):
            prof["persona"] = str(ev.payload["persona"])
            break
    metrics = metrics_for(uid)
    return BootstrapPayload(
        user_id=uid,
        display_name=str(prof.get("display_name") or ""),
        persona=str(prof.get("persona") or "honest"),
        interests=list(prof.get("interests") or []),
        turn_count=int(prof.get("turn_count") or 0),
        fact_hint_count=int(metrics.get("teaches") or 0),
        recent_assets=_recent_assets(uid),
        metrics=metrics,
    )
