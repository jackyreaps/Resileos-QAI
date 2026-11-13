"""Hades lesson notes: an append-only sidecar of lessons and summary metrics.

``Hades`` (hades.py) keeps restorable checkpoints. This sidecar keeps the
short lesson that crosses attempts, one JSON line per note, so a later
attempt or an operator can read what was learned without restoring a
checkpoint.

Contract:
    - Append-only. Notes are never rewritten or reordered. When the file
      reaches ``max_bytes`` a new note is refused, not rotated in.
    - A note is a lesson line plus summary numbers. It never holds full
      history, evidence, scars, prompts, frames, or URLs. Unknown fields
      are dropped, not stored.
    - The path comes from the caller or ``RESILEOS_HADES_NOTES`` and
      defaults to a temp directory, like the residual traces.
    - Not a vector store. No residual state is written.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

NOTE_VERSION = "hades-notes/1"
LESSON_CAP = 240
METRIC_CAP = 12
DEFAULT_MAX_BYTES = 262144
OUTCOMES = frozenset(
    {"verified", "inconclusive", "rejected", "unavailable", "refused", "not_required"}
)
_HEX = set("0123456789abcdef")


def notes_path() -> Path:
    raw = os.environ.get("RESILEOS_HADES_NOTES", "").strip()
    if raw:
        return Path(raw)
    return Path(tempfile.gettempdir()) / "resileos-residual" / "hades-notes.jsonl"


def _hex(value: Any, size: int) -> Optional[str]:
    if isinstance(value, str) and len(value) == size and set(value) <= _HEX:
        return value
    return None


def _lesson(text: Any) -> str:
    line = " ".join(str(text or "").split())
    return line[:LESSON_CAP]


def _metrics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key in sorted(raw, key=str):
        if len(out) >= METRIC_CAP:
            break
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        number = float(value)
        if not math.isfinite(number):
            continue
        name = str(key)[:40]
        out[name] = round(number, 6)
    return out


def build_note(
    *,
    lesson: Any,
    verified: bool = False,
    outcome: str = "inconclusive",
    metrics: Any = None,
    checkpoint_id: Any = None,
    packet_hash: Any = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """The only shape a note can take."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "v": NOTE_VERSION,
        "ts": stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "lesson": _lesson(lesson),
        "verified": bool(verified),
        "outcome": outcome if outcome in OUTCOMES else "inconclusive",
        "metrics": _metrics(metrics),
        "checkpoint_id": _hex(checkpoint_id, 12),
        "packet_hash": _hex(packet_hash, 64),
    }


class HadesNotes:
    """Append-only JSONL of lessons."""

    def __init__(self, path: str | Path | None = None, *, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.path = Path(path) if path is not None else notes_path()
        self.max_bytes = max(0, int(max_bytes))

    def append(self, **fields: Any) -> dict[str, Any]:
        note = build_note(**{k: v for k, v in fields.items() if k in _BUILD_KEYS})
        if not note["lesson"]:
            return {"appended": False, "reason": "empty lesson", "vector_store": False}
        line = json.dumps(note, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        size = self.path.stat().st_size if self.path.exists() else 0
        if size + len(line) > self.max_bytes:
            return {"appended": False, "reason": "notes file is full", "vector_store": False}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="ascii") as handle:
            handle.write(line)
        return {"appended": True, "note": note, "vector_store": False}

    def read(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with open(self.path, encoding="ascii", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        if limit is not None:
            rows = rows[-max(0, int(limit)):] if limit else []
        return rows


_BUILD_KEYS = frozenset({"lesson", "verified", "outcome", "metrics", "checkpoint_id", "packet_hash", "now"})


__all__ = ["HadesNotes", "NOTE_VERSION", "build_note", "notes_path"]
