"""Iris trace sensor: read-only view of the JSONL residual trace.

Iris observes. This sensor opens the trace file for reading only and
returns records and a summary. It never writes the trace, never writes
residual state, never calls learn, and never touches Titanos.

The path is the caller's, or ``RESILEOS_IRIS_JSONL`` (the file
``residual_trace.append_stage`` writes). Malformed lines are counted and
skipped, not raised, so one bad line does not blind the sensor.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from resileos.kin.residual_trace import iris_path

DEFAULT_LIMIT = 500


def read_trace(path: str | Path | None = None, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Last ``limit`` records from the trace. Read-only."""
    target = Path(path) if path is not None else iris_path()
    records: list[dict[str, Any]] = []
    bad = 0
    if target.exists() and target.is_file():
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if isinstance(row, dict):
                    records.append(row)
                else:
                    bad += 1
    cap = max(0, int(limit))
    kept = records[-cap:] if cap else []
    return {
        "path": str(target),
        "exists": target.exists(),
        "records": kept,
        "total": len(records),
        "malformed": bad,
        "wrote": False,
    }


def summarize_trace(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts and means over trace records. Observation only."""
    by_stage: dict[str, int] = {}
    by_result: dict[str, int] = {}
    energies: list[float] = []
    scores: list[float] = []
    for row in records:
        stage = str(row.get("stage") or "unknown")
        result = str(row.get("verify_result") or "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_result[result] = by_result.get(result, 0) + 1
        for key, bucket in (("residual_energy", energies), ("consistency_score", scores)):
            value = row.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                bucket.append(float(value))
    total = len(records)
    verified = by_result.get("verified", 0)
    flags: list[str] = []
    if total >= 5 and verified / total < 0.3:
        flags.append("low_verified_rate")
    if by_result.get("rejected", 0) > verified and by_result.get("rejected", 0) >= 3:
        flags.append("reject_dominant")
    return {
        "records": total,
        "by_stage": by_stage,
        "by_result": by_result,
        "verified_rate": (verified / total) if total else 0.0,
        "mean_residual_energy": (sum(energies) / len(energies)) if energies else None,
        "mean_consistency_score": (sum(scores) / len(scores)) if scores else None,
        "flags": flags,
    }


def observe_trace(path: str | Path | None = None, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """read_trace + summarize_trace. What the Iris legion returns."""
    read = read_trace(path, limit=limit)
    out = {key: value for key, value in read.items() if key != "records"}
    out["summary"] = summarize_trace(read["records"])
    out["last"] = read["records"][-5:]
    return out


__all__ = ["DEFAULT_LIMIT", "observe_trace", "read_trace", "summarize_trace"]
