"""Process-local JSONL traces for a residual clip stage.

Iris and Hades each append one record. The record is the stage, the
packet hash, the residual energy, the consistency score, the verify
result, the budget used, and the checkpoint id. A prompt, a frame, a
URL, and a secret are not fields of this record.

``RESILEOS_IRIS_JSONL`` and ``RESILEOS_HADES_JSONL`` set the files.
``RESILEOS_RESIDUAL_TRACE_CAP_BYTES`` caps each file (default 65536).
When the file would pass the cap, the oldest lines are dropped.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

_FIELDS = (
    "control_id",
    "stage",
    "packet_hash",
    "residual_energy",
    "consistency_score",
    "verify_result",
    "budget_used",
    "checkpoint_id",
)
_STAGES = {"draft", "verify", "upscale"}
_RESULTS = {
    "pending",
    "drafted",
    "verified",
    "inconclusive",
    "rejected",
    "unavailable",
    "not_required",
    "refused",
    "submitted",
}
_DEFAULT_CAP = 65536


def _path(env_name: str, filename: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if raw:
        return Path(raw)
    return Path(tempfile.gettempdir()) / "resileos-residual" / filename


def iris_path() -> Path:
    return _path("RESILEOS_IRIS_JSONL", "iris.jsonl")


def hades_path() -> Path:
    return _path("RESILEOS_HADES_JSONL", "hades.jsonl")


def trace_cap() -> int:
    raw = os.environ.get("RESILEOS_RESIDUAL_TRACE_CAP_BYTES", "").strip()
    if not raw:
        return _DEFAULT_CAP
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_CAP
    return max(0, value)


def _hex_or_blank(value: Any, size: int) -> str:
    if not isinstance(value, str) or len(value) != size:
        return ""
    if any(char not in "0123456789abcdef" for char in value):
        return ""
    return value


def _budget(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"steps": 0, "cost": 0.0}
    try:
        steps = int(value.get("steps", 0))
        cost = float(value.get("cost", 0.0))
    except (TypeError, ValueError):
        return {"steps": 0, "cost": 0.0}
    if steps < 0:
        steps = 0
    if cost < 0 or cost != cost or cost in (float("inf"), float("-inf")):
        cost = 0.0
    return {"steps": steps, "cost": round(cost, 6)}


def scrub_record(record: dict[str, Any]) -> dict[str, Any]:
    """Keep the eight trace fields. Everything else is dropped."""
    stage = str(record.get("stage") or "")
    if stage not in _STAGES:
        stage = "draft"
    result = str(record.get("verify_result") or "")
    if result not in _RESULTS:
        result = "rejected"
    try:
        energy = float(record.get("residual_energy", 0.0))
        score = float(record.get("consistency_score", 0.0))
    except (TypeError, ValueError):
        energy, score = 0.0, 0.0
    if energy != energy or energy in (float("inf"), float("-inf")):
        energy = 0.0
    if score != score or score in (float("inf"), float("-inf")):
        score = 0.0
    control_id = str(record.get("control_id") or "")[:80]
    checkpoint = record.get("checkpoint_id")
    checkpoint_id = checkpoint if _hex_or_blank(checkpoint, 12) else None
    return {
        "control_id": control_id,
        "stage": stage,
        "packet_hash": _hex_or_blank(record.get("packet_hash"), 64),
        "residual_energy": round(energy, 6),
        "consistency_score": round(score, 6),
        "verify_result": result,
        "budget_used": _budget(record.get("budget_used")),
        "checkpoint_id": checkpoint_id,
    }


def _append(path: Path, record: dict[str, Any]) -> None:
    safe = scrub_record(record)
    if set(safe) != set(_FIELDS):
        raise RuntimeError("trace record left the allowed fields")
    line = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload = (line + "\n").encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_bytes() if path.exists() else b""
    data = existing + payload
    cap = trace_cap()
    while len(data) > cap:
        newline = data.find(b"\n")
        if newline < 0:
            data = b""
            break
        data = data[newline + 1 :]
    path.write_bytes(data)


def append_stage(record: dict[str, Any]) -> dict[str, Any]:
    """Append the same scrubbed record to the Iris file and the Hades file."""
    safe = scrub_record(record)
    _append(iris_path(), safe)
    _append(hades_path(), safe)
    return safe


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


__all__ = [
    "append_stage",
    "hades_path",
    "iris_path",
    "read_jsonl",
    "scrub_record",
    "trace_cap",
]
