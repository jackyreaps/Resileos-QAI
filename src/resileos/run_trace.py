"""One structured trace per run, keyed by run id. Outside the residual loop.

``start_run`` opens a run in a context variable. While it is open, the
harness gates (risk, confidence route, budget, residual consistency), Eat
decisions, Zeus reviews, Hades checkpoints, and control-packet events each
append one record to ``RESILEOS_RUN_TRACE`` (JSONL). With no open run,
``emit`` does nothing, so code outside a run is unchanged.

Records hold counts, classes, ids, and hashes. They never hold prompts,
page text, file content, or secrets: every field is whitelisted and
strings are capped. Nothing here calls learn or touches Titanos, and
nothing reads the trace back into a decision. ``read_run``/``replay`` are
the Iris side and open the file read-only.
"""
from __future__ import annotations

import contextvars
import functools
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

KINDS = ("run", "packet", "risk", "route", "budget", "consistency", "eat", "review", "checkpoint", "lesson")
_FIELDS = {
    "run": {"task", "status", "outcome"},
    "packet": {"event", "turn", "packet_id"},
    "risk": {"risk_class", "reason"},
    "route": {"route", "probability"},
    "budget": {"ok", "reason"},
    "consistency": {"ok", "issues"},
    "eat": {"action", "reason"},
    "review": {"applied", "reviewers", "approved", "reason"},
    "checkpoint": {"checkpoint_id", "verified", "packet_hash"},
    "lesson": {"stored", "packet_hash", "loaded"},
}
_CAP = 120
_current: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("resileos_run_id", default=None)
_seq: dict[str, int] = {}
_lock = threading.Lock()


def trace_path() -> Path:
    return Path(os.environ.get("RESILEOS_RUN_TRACE", "data/run_trace.jsonl"))


def current_run() -> Optional[str]:
    return _current.get()


def _clean(kind: str, fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _FIELDS.get(kind, set()):
        if key not in fields:
            continue
        value = fields[key]
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = [str(v)[:40] for v in value][:8]
        else:
            out[key] = str(value)[:_CAP]
    return out


def emit(kind: str, **fields: Any) -> None:
    run_id = _current.get()
    if run_id is None or kind not in KINDS:
        return
    path = trace_path()
    with _lock:
        _seq[run_id] = _seq.get(run_id, 0) + 1
        row = {"run": run_id, "seq": _seq[run_id], "ts": round(time.time(), 3), "kind": kind, **_clean(kind, fields)}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass  # tracing never breaks the turn


@contextmanager
def start_run(task: str = "turn", *, run_id: Optional[str] = None) -> Iterator[str]:
    """Open a run. Nested calls reuse the outer run."""
    outer = _current.get()
    if outer is not None:
        yield outer
        return
    rid = run_id or uuid.uuid4().hex[:16]
    token = _current.set(rid)
    emit("run", task=task, status="start")
    try:
        yield rid
    finally:
        emit("run", task=task, status="end")
        _current.reset(token)
        with _lock:
            _seq.pop(rid, None)


def traced(kind: str, summarize: Callable[[Any], dict[str, Any]]) -> Callable:
    """Decorator: after the call, emit one record built from the result."""

    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            if _current.get() is not None:
                try:
                    emit(kind, **summarize(result))
                except Exception:
                    pass
            return result

        return inner

    return wrap


# ── Iris side: read-only ───────────────────────────────────────────────
def _rows(path: Optional[Path] = None) -> list[dict[str, Any]]:
    p = path or trace_path()
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def list_runs(path: Optional[Path] = None, *, limit: int = 50) -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for row in _rows(path):
        rid = row.get("run")
        info = runs.setdefault(rid, {"run": rid, "task": "", "events": 0, "started": row.get("ts")})
        info["events"] += 1
        if row.get("kind") == "run" and row.get("task"):
            info["task"] = row["task"]
    return sorted(runs.values(), key=lambda r: -(r.get("started") or 0))[:limit]


def read_run(run_id: str, path: Optional[Path] = None) -> list[dict[str, Any]]:
    return sorted((r for r in _rows(path) if r.get("run") == run_id), key=lambda r: r.get("seq", 0))


_EAT = {"accept": "accepted", "reject": "rejected", "abstain": "held back"}


def plain(row: dict[str, Any]) -> str:
    kind = row.get("kind")
    if kind == "run":
        return ("Started " if row.get("status") == "start" else "Finished ") + (row.get("task") or "run")
    if kind == "packet":
        return f"Step {row.get('turn', '?')}: {row.get('event') or 'event'}"
    if kind == "risk":
        return {"allow": "Safety check: allowed", "ask": "Safety check: needs a person to approve",
                "deny": "Safety check: blocked"}.get(row.get("risk_class"), "Safety check")
    if kind == "route":
        return "Confident enough to answer" if row.get("route") != "escalate_or_abstain" else "Not confident: escalate or hold back"
    if kind == "budget":
        return "Within budget" if row.get("ok") else f"Stopped: {row.get('reason') or 'over budget'}"
    if kind == "consistency":
        return "Memory consistent" if row.get("ok") else "Memory inconsistency found"
    if kind == "eat":
        return f"Fact {_EAT.get(row.get('action'), row.get('action'))}" + (f" ({str(row.get('reason')).replace('_', ' ')})" if row.get("reason") not in (None, "", "ok") else "")
    if kind == "review":
        return "Reviewers approved, saved" if row.get("applied") else f"Reviewers did not approve ({row.get('reason') or 'no reason'})"
    if kind == "checkpoint":
        return "Checkpoint saved" + (" (verified)" if row.get("verified") else "")
    if kind == "lesson":
        if row.get("loaded") is not None:
            return f"Loaded {row.get('loaded')} past lesson(s)"
        return "Lesson stored" if row.get("stored") else "Lesson not stored (cycle not verified)"
    return str(kind)


def replay(run_id: str, path: Optional[Path] = None) -> dict[str, Any]:
    rows = read_run(run_id, path)
    return {"run": run_id, "steps": [{"seq": r.get("seq"), "kind": r.get("kind"), "text": plain(r), "data": r} for r in rows]}


__all__ = ["KINDS", "current_run", "emit", "list_runs", "plain", "read_run", "replay", "start_run", "trace_path", "traced"]
