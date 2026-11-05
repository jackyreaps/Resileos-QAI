"""Seeded evolution unit tests (no Titanos / FastAPI required)."""
from __future__ import annotations

from pathlib import Path

import resileos.seed.log as seed_log
from resileos.seed.evolution import (
    bootstrap,
    record_asset,
    record_event,
    record_learn,
    record_query_result,
)
from resileos.seed.log import append_event, iter_events
from resileos.seed.metrics import metrics_for, metrics_from_events
from resileos.seed.types import SeedEvent


def test_append_and_iter(tmp_path: Path, monkeypatch):
    log = tmp_path / "seed.jsonl"
    monkeypatch.setattr(seed_log, "default_log_path", lambda: log)
    ev = SeedEvent(ts="2026-01-01T00:00:00Z", user_id="alice", event_type="session_start", payload={})
    assert append_event(ev, path=log) is True
    rows = iter_events("alice", path=log)
    assert len(rows) == 1
    assert rows[0].user_id == "alice"


def test_record_learn_and_metrics(tmp_path: Path, monkeypatch):
    log = tmp_path / "seed.jsonl"
    monkeypatch.setattr(seed_log, "default_log_path", lambda: log)
    record_learn("bob", "Zeus", "domain", "sky")
    record_query_result("bob", "Zeus", "domain", hit=True)
    record_query_result("bob", "Hera", "domain", hit=False)
    m = metrics_for("bob")
    assert m["teaches"] == 1
    assert m["hits"] == 1
    assert m["misses"] == 1
    assert m["queries"] == 2
    assert abs(m["hit_rate"] - 0.5) < 1e-9


def test_record_asset_and_bootstrap(tmp_path: Path, monkeypatch):
    log = tmp_path / "seed.jsonl"
    monkeypatch.setattr(seed_log, "default_log_path", lambda: log)
    record_asset("cara", "a1", "image", "https://example.com/x.png", title="x")
    record_event("cara", "persona_set", {"persona": "guide"})
    boot = bootstrap("cara", session=True)
    assert boot.user_id == "cara"
    assert boot.persona == "guide"
    assert boot.metrics["assets"] >= 1
    assert any(a.get("asset_id") == "a1" for a in boot.recent_assets)
    assert boot.metrics["sessions"] >= 1


def test_append_failure_soft(tmp_path: Path, monkeypatch):
    bad = tmp_path / "missing" / "nope.jsonl"
    # parent missing and we still try — mkdir should work; use unwritable by mocking open
    ev = SeedEvent(ts="t", user_id="x", event_type="session_start", payload={})
    # Point at a path whose parent is a file → mkdir fails
    file_blocker = tmp_path / "blocker"
    file_blocker.write_text("x", encoding="utf-8")
    path = file_blocker / "seed.jsonl"
    assert append_event(ev, path=path) is False


def test_metrics_from_empty():
    assert metrics_from_events([])["hit_rate"] == 0.0
