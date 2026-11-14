"""Streaming chat: typed parts, mouth policy, resume, cancel, owner isolation."""
import asyncio
import json
import re
from pathlib import Path

import pytest

import resileos.chat.assist as A
from resileos.chat import stream as S

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def bypass(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)


def parse(text):
    events = []
    for block in text.split("\n\n"):
        data = [l[6:] for l in block.splitlines() if l.startswith("data: ")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events


def test_schema_matches_the_browser_copy():
    js = (ROOT / "landing" / "public" / "assets" / "stream-parts.js").read_text()
    block = js.split("var SCHEMA = {", 1)[1].split("};", 1)[0]
    found = dict(re.findall(r'(\w+): \[([^\]]*)\]', block))
    assert set(found) == set(S.PART_SCHEMA)
    for kind, fields in found.items():
        assert tuple(f.strip().strip('"') for f in fields.split(",") if f.strip()) == S.PART_SCHEMA[kind], kind
    with pytest.raises(ValueError):
        S.part("nope")
    assert S.part("token", content="x", verified=True, secret="no") == {"v": 1, "type": "token", "content": "x", "verified": True}


def _fake(reply, delay=0.0):
    async def run_assist(body, **kw):
        on = kw.get("on_event")
        on({"type": "step", "step": "lean", "status": "running", "label": "Checking your proof"})
        await asyncio.sleep(delay)
        on({"type": "step", "step": "lean", "status": "done", "label": "Checked your proof: it checks"})
        return {**reply, "assist": {"trail": [{"step": "lean", "label": "Checked your proof: it checks", "status": "done"}],
                                    "attachments": [{"name": "a.png", "address": "b5/f5", "code": "C1", "dominant": "red"}],
                                    "sources": []}}
    return run_assist


def test_unverified_reply_arrives_once_and_labelled(client, monkeypatch):
    monkeypatch.setattr(A, "run_assist", _fake({"status": "ACCEPTED", "reply_text": "maybe it is blue", "verified": False}))
    res = client.post("/api/v1/chat/stream", json={"message": "what colour?"})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    events = parse(res.text)
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done" and "final" in types
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    tokens = [e for e in events if e["type"] == "token"]
    assert tokens == [{"v": 1, "type": "token", "content": "maybe it is blue", "verified": False, "seq": tokens[0]["seq"]}]
    steps = [e for e in events if e["type"] == "step"]
    assert [s["status"] for s in steps] == ["running", "done"]
    assert any(e["type"] == "address" and e["code"] == "C1" for e in events)
    assert any(e["type"] == "harness" and e["verified"] is False for e in events)


def test_verified_reply_streams_tokens_only_when_mouth_allows(client, monkeypatch):
    monkeypatch.setattr(A, "run_assist", _fake({"status": "ACCEPTED", "reply_text": "Zeus rules the sky", "verified": True}))
    import resileos.kin.mouth_policy as M

    monkeypatch.setattr(M, "should_render_prose", lambda requested, **k: True)
    events = parse(client.post("/api/v1/chat/stream", json={"message": "zeus?"}).text)
    toks = [e["content"] for e in events if e["type"] == "token"]
    assert len(toks) == 4 and "".join(toks) == "Zeus rules the sky"
    monkeypatch.setattr(M, "should_render_prose", lambda requested, **k: False)
    events = parse(client.post("/api/v1/chat/stream", json={"message": "zeus?"}).text)
    assert [e["verified"] for e in events if e["type"] == "token"] == [False]


def test_abstain_is_explicit(client, monkeypatch):
    monkeypatch.setattr(A, "run_assist", _fake({"status": "NO_ROWS", "reply_text": "Nothing saved.", "verified": False}))
    events = parse(client.post("/api/v1/chat/stream", json={"message": "x"}).text)
    assert any(e["type"] == "abstain" and e["label"] == "Nothing saved about that" for e in events)


def test_resume_replays_after_a_given_part(client, monkeypatch):
    monkeypatch.setattr(A, "run_assist", _fake({"status": "ACCEPTED", "reply_text": "ok", "verified": False}))
    first = client.post("/api/v1/chat/stream", json={"message": "x"})
    sid = first.headers["x-stream-id"]
    full = parse(first.text)
    again = parse(client.get(f"/api/v1/chat/stream/{sid}?after=3").text)
    assert again == full[3:]
    by_header = parse(client.get(f"/api/v1/chat/stream/{sid}", headers={"Last-Event-ID": "5"}).text)
    assert by_header == full[5:]
    assert client.get("/api/v1/chat/stream/" + "0" * 32).status_code == 404


def test_cancel_stops_the_turn():
    async def go():
        stream = S.HUB.create("me")

        async def slow(body, on_event):
            on_event({"type": "step", "step": "lean", "status": "running", "label": "Checking your proof"})
            await asyncio.sleep(30)
            return {}

        stream.task = asyncio.ensure_future(S.produce(stream, object(), run=slow, prose_allowed=lambda r: False))
        await asyncio.sleep(0.1)
        stream.task.cancel()
        try:
            await stream.task
        except asyncio.CancelledError:
            pass
        return [e["type"] for e in stream.events]

    types = asyncio.run(go())
    assert "final" not in types and types[-2:] == ["cancelled", "done"]


def test_streams_belong_to_their_owner():
    hub = S.StreamHub()
    s = hub.create("acct:a")
    assert hub.get(s.id, "acct:a") is s and hub.get(s.id, "acct:b") is None


def test_stream_paths_are_public_on_both_sides():
    from middleware import proxy_identity as P

    assert P.is_public("POST", "/api/v1/chat/stream") and P.is_public("GET", "/api/v1/chat/stream/abc")
    assert P.is_public("POST", "/api/v1/chat/stream/abc/cancel")
