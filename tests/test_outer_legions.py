"""Outer-layer legions: Hermes envelopes, sandbox gate, Iris trace, Hades notes."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.kin.eat_envelope import check_envelope
from resileos.kin.hades_notes import HadesNotes, build_note
from resileos.kin.iris_trace import observe_trace, read_trace
from resileos.kin.legions import LegionError, invoke_legion, kin_catalogue, reset_legions
from resileos.kin.outer_legions import (
    crawl_envelope,
    register_outer_legions,
    review_proof_verified,
    sandbox_request,
    search_envelopes,
)
from resileos.kin.residual_trace import append_stage


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    reset_legions()
    monkeypatch.setenv("RESILEOS_IRIS_JSONL", str(tmp_path / "iris.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_JSONL", str(tmp_path / "hades.jsonl"))
    yield
    reset_legions()


def _packet(**overrides):
    packet = {
        "id": "outer",
        "budget_remaining": {"steps": 5, "cost": 1.0, "tokens": 100},
        "evidence": [],
        "history": [{"event": "private-history"}],
        "scars": [],
        "verified": False,
        "lesson": "the lesson",
    }
    packet.update(overrides)
    return packet


def _fake_search(calls):
    def search(query, max_results=3):
        calls.append((query, max_results))
        return {
            "status": "SUCCESS",
            "query": query,
            "results": [
                {"title": "<b>Athens</b> &amp; Greece", "url": "https://a.example/1", "snippet": "Athens is the capital."},
                {"title": "Second", "url": "https://a.example/2", "snippet": ""},
                {"title": "No url", "url": "", "snippet": "dropped"},
            ],
        }

    return search


# ── Hermes search / crawl ─────────────────────────────────────────────
def test_off_by_default():
    assert register_outer_legions() == []
    for kin in ("hermes", "iris", "hades"):
        assert kin_catalogue(kin) == []


def test_search_envelopes_copy_backend_text_and_invent_nothing():
    calls = []
    out = search_envelopes("capital of greece", search_fn=_fake_search(calls), max_results=3)
    assert calls == [("capital of greece", 3)]
    assert out["status"] == "OK"
    envs = out["envelopes"]
    assert [e["source"] for e in envs] == ["https://a.example/1", "https://a.example/2"]
    assert envs[0]["title"] == "Athens & Greece"
    assert envs[0]["snippet"] == "Athens is the capital."
    assert envs[1]["snippet"] == ""  # empty stays empty
    for env in envs:
        assert env["trust"] == "untrusted"
        assert env["claim"] is None
        assert "Extracted" not in json.dumps(env)
        # An envelope from Hermes cannot become a fact on its own.
        assert check_envelope(env).action == "abstain"


def test_async_backend_is_supported():
    async def search(query, max_results=3):
        return {"status": "SUCCESS", "results": [{"title": "t", "url": "https://x.example", "snippet": "s"}]}

    out = search_envelopes("q", search_fn=search)
    assert out["envelopes"][0]["snippet"] == "s"


@pytest.mark.parametrize(
    "backend",
    [
        lambda q, max_results=3: {"status": "ERROR", "error": "blocked", "results": []},
        lambda q, max_results=3: (_ for _ in ()).throw(OSError("offline")),
    ],
)
def test_backend_failure_is_unavailable_not_fabricated(backend):
    out = search_envelopes("q", search_fn=backend)
    assert out["status"] == "UNAVAILABLE"
    assert out["envelopes"] == []


def test_crawl_envelope_uses_page_text_only():
    out = crawl_envelope(
        "https://x.example/p",
        fetch_fn=lambda url: {"status": "SUCCESS", "url": url, "content": "<p>Hello   world</p>"},
    )
    assert out["envelopes"][0]["text"] == "Hello world"
    assert crawl_envelope("file:///etc/passwd", fetch_fn=lambda u: {})["status"] == "UNAVAILABLE"


def test_hermes_legion_is_escalate_only_and_cannot_learn():
    calls = []
    register_outer_legions(enable=True, search_fn=_fake_search(calls))
    with pytest.raises(LegionError, match="escalate"):
        invoke_legion("hermes", "search_envelope", _packet(), probability=0.99, query="q")
    assert calls == []
    out = invoke_legion("hermes", "search_envelope", _packet(), probability=0.2, query="q")
    assert out["status"] == "OK"
    assert out["verified"] is False
    assert out["gated_write"] is False
    with pytest.raises(LegionError, match="learn is gated"):
        invoke_legion("hermes", "search_envelope", _packet(), probability=0.2, query="q", learn_fn=print)


# ── Hermes sandbox gate ───────────────────────────────────────────────
def _proof(approved=True, verified=True):
    return {
        "applied": approved,
        "verdicts": [{"reviewer": "verifiers", "approved": approved}],
        "verification": {"verified": verified},
    }


def test_sandbox_not_registered_without_its_own_flag():
    register_outer_legions(enable=True, search_fn=_fake_search([]))
    names = [row["name"] for row in kin_catalogue("hermes")]
    assert "sandbox_request" not in names


def test_sandbox_refuses_then_is_unavailable_and_never_executes():
    assert sandbox_request()["status"] == "REFUSED"
    assert sandbox_request(risk_class="ask", review=_proof())["status"] == "REFUSED"
    assert sandbox_request(risk_class="allow", review=_proof(verified=False))["status"] == "REFUSED"
    assert sandbox_request(risk_class="allow", review=_proof(approved=False))["status"] == "REFUSED"
    cleared = sandbox_request(risk_class="allow", review=_proof())
    assert cleared["status"] == "UNAVAILABLE"
    assert cleared["executed"] is False and cleared["url"] is None
    assert review_proof_verified({"applied": True, "verdicts": [], "verification": {"verified": True}}) is False

    register_outer_legions(enable=True, enable_sandbox=True, search_fn=_fake_search([]))
    out = invoke_legion("hermes", "sandbox_request", _packet(), risk_class="allow", review=_proof(), code="print(1)")
    assert out["status"] == "UNAVAILABLE"
    assert out["executed"] is False


# ── Iris trace sensor ─────────────────────────────────────────────────
def test_iris_trace_is_read_only_and_tolerates_bad_lines(tmp_path):
    path = tmp_path / "iris.jsonl"
    append_stage({"control_id": "c1", "stage": "verify", "verify_result": "verified", "residual_energy": 0.1})
    append_stage({"control_id": "c2", "stage": "draft", "verify_result": "rejected", "residual_energy": 0.3})
    with open(path, "a", encoding="ascii") as handle:
        handle.write("{not json\n")
    before = path.read_bytes()
    out = observe_trace(path)
    assert path.read_bytes() == before
    assert out["wrote"] is False
    assert out["total"] == 2 and out["malformed"] == 1
    assert out["summary"]["by_result"] == {"verified": 1, "rejected": 1}
    assert out["summary"]["mean_residual_energy"] == pytest.approx(0.2)
    # default path comes from RESILEOS_IRIS_JSONL
    assert read_trace()["total"] == 2
    assert read_trace(tmp_path / "missing.jsonl")["exists"] is False


def test_iris_legion_refuses_writes(tmp_path):
    register_outer_legions(enable=True, trace_path=str(tmp_path / "iris.jsonl"))
    out = invoke_legion("iris", "trace_sensor", _packet())
    assert out["wrote"] is False
    with pytest.raises(LegionError, match="iris"):
        invoke_legion("iris", "trace_sensor", _packet(), write_residual=True)


# ── Hades notes ───────────────────────────────────────────────────────
def test_hades_notes_keep_lesson_and_numbers_only(tmp_path):
    notes = HadesNotes(tmp_path / "n.jsonl")
    first = notes.append(
        lesson="line one\nline two " + "x" * 400,
        verified=True,
        outcome="verified",
        metrics={"energy": 0.25, "flag": True, "text": "drop", "nan": float("nan")},
        checkpoint_id="abcdef012345",
        packet_hash="not-a-hash",
    )
    assert first["appended"] is True
    note = notes.read()[0]
    assert "\n" not in note["lesson"] and len(note["lesson"]) == 240
    assert note["metrics"] == {"energy": 0.25}
    assert note["checkpoint_id"] == "abcdef012345"
    assert note["packet_hash"] is None
    assert "history" not in note and "evidence" not in note and "scars" not in note


def test_hades_notes_are_append_only_and_refuse_past_cap(tmp_path):
    path = tmp_path / "n.jsonl"
    notes = HadesNotes(path, max_bytes=400)
    assert notes.append(lesson="a")["appended"]
    first = path.read_bytes()
    assert notes.append(lesson="b")["appended"]
    assert path.read_bytes().startswith(first)
    while notes.append(lesson="c" * 50)["appended"]:
        pass
    assert path.stat().st_size <= 400
    assert notes.append(lesson="")["appended"] is False
    assert build_note(lesson="x", outcome="bogus")["outcome"] == "inconclusive"


def test_hades_legion_drops_history(tmp_path):
    register_outer_legions(enable=True, notes_path=str(tmp_path / "n.jsonl"))
    out = invoke_legion("hades", "lesson_note", _packet(), outcome="rejected", history=[{"secret": 1}])
    assert out["appended"] is True
    raw = (tmp_path / "n.jsonl").read_text()
    assert "private-history" not in raw and "secret" not in raw
    assert json.loads(raw)["lesson"] == "the lesson"
