"""Append-only JSONL seed event log (volume-friendly)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from resileos.seed.types import SeedEvent


def default_log_path() -> Path:
    explicit = os.getenv("RESILEOS_SEED_LOG", "").strip()
    if explicit:
        return Path(explicit)
    # repo-relative default for venv; /app/data in container if present
    app_data = Path("/app/data/seed_events.jsonl")
    if Path("/app/data").is_dir():
        return app_data
    root = Path(__file__).resolve().parents[3]
    return root / "data" / "seed_events.jsonl"


def append_event(event: SeedEvent, path: Path | None = None) -> bool:
    """Write one event. Returns False on failure (never raises to callers)."""
    p = path or default_log_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
        return True
    except OSError:
        return False


def iter_events(
    user_id: str | None = None,
    *,
    limit: int = 500,
    path: Path | None = None,
) -> list[SeedEvent]:
    """Read events (full file scan; fine for early scale). Newest last."""
    p = path or default_log_path()
    if not p.exists():
        return []
    out: list[SeedEvent] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = SeedEvent.from_dict(json.loads(line))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if user_id and ev.user_id != user_id:
                    continue
                out.append(ev)
    except OSError:
        return []
    if limit and len(out) > limit:
        return out[-limit:]
    return out
