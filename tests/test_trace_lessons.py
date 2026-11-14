"""Run traces (read-only replay) and lesson memory (lesson + hash only)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from resileos import run_trace as RT
from resileos.harness.packet import ControlPacket
from resileos.harness.tools import confidence_route, residual_consistency, risk_classify
from resileos.kin.eat import eat_filter
from resileos.kin.eat_envelope import eat_commit_envelopes
from resileos.kin.hades import Hades
from resileos.kin.lesson_store import LessonStore

from test_eat_envelope import _env, _titanos


@pytest.fixture(autouse=True)
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("RESILEOS_RUN_TRACE", str(tmp_path / "trace.jsonl"))
    monkeypatch.setenv("RESILEOS_LESSONS_DIR", str(tmp_path / "lessons"))
    return tmp_path


def test_no_run_means_no_trace(paths):
    risk_classify("read file")
    eat_filter("Zeus domain sky")
    assert not (paths / "trace.jsonl").exists()


def test_one_run_records_every_kind_with_no_content(paths):
    secret = "my PIN is 4321 and I live at 9 Elm St"
    with RT.start_run("demo") as rid:
        pkt = ControlPacket(id="p1")
        pkt.append({"event": "draft", "text": secret})
        risk_classify("send " + secret)
        confidence_route({"probability": 0.2})
        residual_consistency({"scars": ["s1"], "evidence": []})
        eat_filter({"subject": "Zeus", "relation": "domain", "obj": secret})
        Hades(paths / "hades").save(pkt, residual_packet_hash="ab" * 32, lesson="keep it short")
    rows = RT.read_run(rid)
    kinds = [r["kind"] for r in rows]
    for kind in ("run", "packet", "risk", "route", "consistency", "eat", "checkpoint"):
        assert kind in kinds, kind
    raw = (paths / "trace.jsonl").read_text()
    assert "4321" not in raw and "Elm" not in raw and "keep it short" not in raw
    steps = [s["text"] for s in RT.replay(rid)["steps"]]
    assert steps[0] == "Started demo" and steps[-1] == "Finished demo"
    assert "Safety check: needs a person to approve" in steps
    assert "Not confident: escalate or hold back" in steps
    assert "Memory inconsistency found" in steps
    assert RT.list_runs()[0]["run"] == rid


def test_lessons_need_a_verified_cycle_and_store_only_lesson_and_hash(paths):
    store = LessonStore("ada")
    refused = store.record("x", "ab" * 32, review={"applied": False})
    assert refused["stored"] is False and store.rows() == []
    with RT.start_run("commit") as rid:
        out = eat_commit_envelopes([_env("Athens", "capital_of", "Greece", "1834-01-01")], titanos=_titanos(), lessons=store)
    assert out["summary"]["applied"] is True
    rows = store.rows()
    assert len(rows) == 1 and set(rows[0]) == {"lesson", "packet_hash", "ts"}
    assert "Athens" not in json.dumps(rows)  # no facts, no trace in lesson memory
    assert "Lesson stored" in [s["text"] for s in RT.replay(rid)["steps"]]


def test_fresh_packet_loads_relevant_lessons_without_history(paths):
    store = LessonStore("ada")
    ok = {"applied": True, "verdicts": [{"approved": True}], "verification": {"verified": True}}
    store.record("lean proofs need the full file, not a snippet", "aa" * 32, review=ok)
    store.record("image uploads read best at belt five", "bb" * 32, review=ok)
    pkt = ControlPacket(id="fresh")
    ids = store.load_into(pkt, "check this lean proof file", k=1)
    assert ids == ["lesson:" + "aa" * 6]
    assert pkt.guide_bodies[ids[0]].startswith("lean proofs") and pkt.history == []


def test_lesson_memory_is_outside_the_residual_loop():
    src = (ROOT / "src" / "resileos" / "kin" / "lesson_store.py").read_text()
    trace = (ROOT / "src" / "resileos" / "run_trace.py").read_text()
    for text in (src, trace):
        assert ".learn(" not in text and "titanos" not in text.lower().replace("touches titanos", "")


def test_equal_budget_script_reports_counted_numbers():
    import harness_equal_budget as hb

    out = hb.main()
    a, b = out["without_harness"], out["with_harness"]
    assert out["budget"] == 40 and a["writes"] == 40
    assert b["correct_stored"] == 16 and b["wrong_stored"] == 0 and b["duplicates_written"] == 0
    assert a["wrong_stored"] > 0


def test_runs_endpoints_are_admin_only(client, monkeypatch):
    import app as app_module
    from test_proxy_identity import admin_headers

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv("RESILEOS_PROXY_SECRET", "proxy-secret-value")
    monkeypatch.setenv("RESILEOS_API_KEYS", '{"user-key":{"name":"ada","tier":"free","quota":500}}')
    assert client.get("/api/v1/runs", headers={"X-API-Key": "user-key"}).status_code == 403
    with RT.start_run("api") as rid:
        risk_classify("read")
    ok = client.get("/api/v1/runs", headers={"X-API-Key": "user-key", **admin_headers("GET", "/runs")})
    assert ok.status_code == 200 and ok.json()["runs"][0]["run"] == rid
    one = client.get(f"/api/v1/runs/{rid}", headers={"X-API-Key": "user-key", **admin_headers("GET", f"/runs/{rid}")})
    assert one.status_code == 200 and one.json()["steps"][0]["text"] == "Started api"


def test_coherence_is_read_from_the_trace_with_real_counts(paths):
    assert RT.coherence()["runs"] == 0 and RT.coherence()["residual_consistency"] is None
    with RT.start_run("a"):
        residual_consistency({"scars": [], "evidence": []})
        residual_consistency({"scars": ["s1"], "evidence": []})
        confidence_route({"probability": 0.2})
        confidence_route({"probability": 0.995})
    with RT.start_run("b"):
        pkt = ControlPacket(id="p2", verified=True)
        Hades(paths / "hades").save(pkt, residual_packet_hash="cd" * 32, lesson="x")
    out = RT.coherence()
    assert out["runs"] == 2
    assert out["residual_consistency"] == 0.5 and out["counts"]["consistency"] == 2
    assert out["abstain_rate"] == 0.5
    assert out["verification_rate"] == 1.0 and out["counts"]["decided_runs"] == 1
    assert out["correct_abstention"] is None  # needs labels: held-out suite


def test_held_out_suite_reports_guarded_metrics():
    import harness_equal_budget as hb
    from resileos.persona.upgrade_report import COHERENCE_METRICS

    out = hb.held_out()
    for name in COHERENCE_METRICS:
        assert 0.0 <= out[name] <= 1.0, name
    assert out["residual_consistency"] == 1.0 and out["counts"]["eat_held_back"] == 24
    assert out["counts"]["answered"] == 13 and out["counts"]["right_answered"] == 11


def test_coherence_endpoint_is_admin_only(client, monkeypatch):
    import app as app_module
    from test_proxy_identity import admin_headers

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv("RESILEOS_PROXY_SECRET", "proxy-secret-value")
    monkeypatch.setenv("RESILEOS_API_KEYS", '{"user-key":{"name":"ada","tier":"free","quota":500}}')
    assert client.get("/api/v1/coherence", headers={"X-API-Key": "user-key"}).status_code == 403
    ok = client.get("/api/v1/coherence?held_out=true",
                    headers={"X-API-Key": "user-key", **admin_headers("GET", "/coherence")})
    assert ok.status_code == 200
    body = ok.json()
    assert "trace" in body and body["held_out"]["suite"].startswith("held-out")
    assert body["guarded"]["residual_consistency"].startswith("L0")
