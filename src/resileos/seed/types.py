"""Types for seeded evolution."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SeedEvent:
    ts: str
    user_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeedEvent:
        return cls(
            ts=str(data.get("ts", "")),
            user_id=str(data.get("user_id", "")),
            event_type=str(data.get("event_type", "")),
            payload=dict(data.get("payload") or {}),
        )


@dataclass
class BootstrapPayload:
    user_id: str
    display_name: str = ""
    persona: str = "honest"
    interests: list[str] = field(default_factory=list)
    turn_count: int = 0
    fact_hint_count: int = 0
    recent_assets: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EVENT_TYPES = frozenset(
    {
        "session_start",
        "fact_learned",
        "query_hit",
        "query_miss",
        "asset_registered",
        "persona_set",
        "mouth_used",
    }
)
