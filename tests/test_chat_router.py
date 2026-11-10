"""Router classes, hub ledger, and the tool-mouth demo's alice path."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from resileos.chat.ledger import (
    delete_user_triple,
    edit_user_triple,
    list_user_ledger,
)
from resileos.chat.router import Turn, classify, dispatch
from titanos import Titanos, TitanosConfig

ROOT = Path(__file__).resolve().parents[1]


def _store() -> Titanos:
    titan = Titanos(
        TitanosConfig(dim=256, m=16, n=16, r=2, n_loops=1, seed=0, emergent=False)
    )
    titan.learn("Zeus", "domain", "sky")
    titan.learn("Poseidon", "domain", "sea")
    return titan


class _Counting:
    def __init__(self, inner: Titanos) -> None:
        self.inner = inner
        self.calls: list[str] = []

    def learn(self, *args, **kwargs):
        self.calls.append("learn")
        return self.inner.learn(*args, **kwargs)

    def ask_list(self, *args, **kwargs):
        self.calls.append("ask_list")
        return self.inner.ask_list(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.inner, name)


def test_classify_order():
    store = _store()
    assert classify("remember that I prefer tea", store) == "HUB_LEARN"
    assert classify("I prefer tea", store) == "HUB_LEARN"
    assert classify("my theme is dark", store) == "HUB_LEARN"
    assert classify("what do I prefer", store) == "HUB_RECALL"
    assert classify("in my workspace", store) == "HUB_RECALL"
    assert classify("what is the domain of Zeus", store) == "TOOL_FACT"
    assert classify("Zeus domain", store) == "TOOL_FACT"
    assert (
        classify("what is the domain of Zeus", store, last_tool_empty=True)
        == "TOOL_FACT"
    )
    assert classify("and then?", store, last_tool_empty=True) == "ABSTAIN_SURFACE"
    assert classify("remember that I prefer tea", store, last_tool_empty=True) == "HUB_LEARN"
    assert classify("hello", store) == "SOFT_CHAT"
    assert classify("hello", store, last_tool_empty=False) == "SOFT_CHAT"


def test_every_class_dispatch():
    store = _store()
    reply, status, action = dispatch(
        Turn("remember that I prefer exact_answers", allow_mouth=True),
        store,
        "alice",
    )
    assert action["class"] == "HUB_LEARN"
    assert status == "ACCEPTED"
    assert action["subject"] == "user:alice"
    assert action["relation"] == "prefers"
    assert action["obj"] == "exact_answers"
    assert action["wrote"] is True
    assert "user:alice prefers exact_answers" in reply

    reply, status, action = dispatch(
        Turn("what do I prefer", allow_mouth=True), store, "alice"
    )
    assert action["class"] == "HUB_RECALL"
    assert status == "ACCEPTED"
    assert action["rows"] == ["exact_answers"]
    assert reply == "user:alice prefers exact_answers."
    assert "sea" not in reply

    reply, status, action = dispatch(
        Turn("what is the domain of Zeus", allow_mouth=True), store, "alice"
    )
    assert action["class"] == "TOOL_FACT"
    assert status == "ACCEPTED"
    assert action["rows"] == ["sky"]
    assert reply == "Zeus domain sky."
    assert "sea" not in reply
    assert action["tool"] == "resileos_ask"

    reply, status, action = dispatch(
        Turn("hello", allow_mouth=True, persona="builder"), store, "alice"
    )
    assert action["class"] == "SOFT_CHAT"
    assert action["tool"] is None
    assert action["wrote"] is False
    assert status == "ACCEPTED"
    assert "next step" in reply
    assert "sky" not in reply

    reply, status, action = dispatch(
        Turn("and then?", allow_mouth=True, last_tool_empty=True), store, "alice"
    )
    assert action["class"] == "ABSTAIN_SURFACE"
    assert status == "ABSTAINED"
    assert action["action"] == "abstain"
    assert "remember that" in reply
    assert action["rows"] == []


def test_hub_user_alice_matches_demo_triple():
    """Same prefers/exact_answers triple as tool_mouth_demo --hub-user alice.

    The demo stores the raw id. The router stores the namespace subject.
    """
    store = _store()
    dispatch("remember that I prefer exact_answers", store, "alice")
    assert store.ask_list("user:alice", "prefers") == ["exact_answers"]
    reply, status, action = dispatch("what do I prefer", store, "Alice")
    assert action["subject"] == "user:alice"
    assert status == "ACCEPTED"
    assert "exact_answers" in reply


def test_tool_mouth_demo_hub_user_alice():
    report = ROOT / "artifacts" / "report_tool_mouth_demo.json"
    original = report.read_bytes() if report.exists() else None
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "tool_mouth_demo.py"), "--hub-user", "alice"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        payload = json.loads(report.read_text(encoding="utf-8"))
        hub = [
            row
            for row in payload["transcript"]
            if row["arguments"].get("subject") == "alice"
            and row["arguments"].get("relation") == "prefers"
        ]
        assert hub
        assert "exact_answers" in hub[0]["oracle"]["rows"]
        assert "exact_answers" in hub[0]["mouth"]
        assert "alice" in proc.stdout
    finally:
        if original is None:
            report.unlink(missing_ok=True)
        else:
            report.write_bytes(original)


def test_soft_chat_calls_no_tools_and_mouth_gate():
    counted = _Counting(_store())
    reply, status, action = dispatch(
        Turn("hello there", allow_mouth=False), counted, "alice"
    )
    assert action["class"] == "SOFT_CHAT"
    assert counted.calls == []
    assert reply == ""
    assert status == "MOUTH_CLOSED"

    reply, status, action = dispatch(
        Turn("what is the domain of Zeus", allow_mouth=False), counted, "alice"
    )
    assert reply == "sky"
    assert "Zeus domain" not in reply
    assert status == "ACCEPTED"
    assert "learn" not in counted.calls


def test_unknown_fact_does_not_invent():
    store = _store()
    reply, status, action = dispatch(
        "what is the domain of Nobody", store, "alice"
    )
    assert action["class"] == "TOOL_FACT"
    assert status == "NO_ROWS"
    assert action["rows"] == []
    assert "sky" not in reply
    assert "sea" not in reply


def test_temporal_conflict_chip_status():
    store = _store()
    store.learn(
        "Athens", "capital_of", "Ottoman",
        valid_from="2000-01-01", valid_to="2099-01-01",
    )
    store.learn(
        "Athens", "capital_of", "Greece",
        valid_from="2000-01-01", valid_to="2099-01-01",
    )
    reply, status, action = dispatch(
        Turn("what is Athens's capital_of", allow_mouth=True), store, "alice"
    )
    assert status == "CONFLICT"
    assert action["class"] == "TOOL_FACT"
    assert set(action["rows"]) == {"Ottoman", "Greece"}
    assert "Ottoman" in reply and "Greece" in reply


def test_force_remember_and_world_recall():
    store = _store()
    _, status, action = dispatch(
        Turn("hello there", force_class="HUB_LEARN", allow_mouth=False),
        store,
        "alice",
    )
    assert action["class"] == "HUB_LEARN"
    assert action["relation"] == "note"
    assert status == "ACCEPTED"
    assert store.ask_list("user:alice", "note") == ["hello there"]

    store.learn("world:demo", "prefers", "maps")
    reply, status, action = dispatch("what does world:demo prefer", store, "alice")
    assert action["class"] == "HUB_RECALL"
    assert action["subject"] == "world:demo"
    assert action["rows"] == ["maps"]
    assert "maps" in reply


def test_my_name_is_stated_not_global():
    store = _store()
    _, _, action = dispatch("my name is Ada", store, "alice")
    assert action["subject"] == "user:alice"
    assert action["relation"] == "stated"
    assert action["obj"] == "name=Ada"
    assert store.ask_list("Ada", "name") == []


def test_ledger_list_edit_delete_uses_ask_list():
    store = _store()
    dispatch("remember that I prefer exact_answers", store, "alice")
    ledger = list_user_ledger(store, "alice")
    assert ledger["subject"] == "user:alice"
    assert ledger["triples"][0]["obj"] == "exact_answers"
    edited = edit_user_triple(
        store,
        "alice",
        "prefers",
        "exact_answers",
        new_obj="short_answers",
    )
    assert edited["wrote"] is True
    assert store.ask_list("user:alice", "prefers") == ["short_answers"]
    removed = delete_user_triple(store, "alice", "prefers", "short_answers")
    assert removed["removed"] == 1
    assert removed["triples"] == []
    with pytest.raises(KeyError):
        delete_user_triple(store, "alice", "prefers", "short_answers")
