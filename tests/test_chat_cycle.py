"""Ordinary chat runs a bounded Kin cycle and keeps history."""
from __future__ import annotations

import uuid
from pathlib import Path

from resileos.chat.turn_cycle import budget_history, continuation_text
from resileos.harness.cascade import CascadeRouter
from resileos.harness.packet import ControlPacket
from resileos.harness.tools import decision_fanout

ROOT = Path(__file__).resolve().parents[1]


class _Names:
    relations = {"domain": "domain"}
    entities = {"zeus2": "zeus2"}


def test_history_budget_keeps_the_recent_window():
    history = [{"role": "user", "content": f"turn {index}"} for index in range(12)]
    window = budget_history(history)
    assert len(window) == 8
    assert window[0]["content"] == "turn 4"
    assert window[-1]["content"] == "turn 11"


def test_continuation_reuses_the_prior_relation():
    window = budget_history(
        [
            {"role": "user", "content": "what is the domain of poseidon2"},
            {
                "role": "assistant",
                "content": "poseidon2 domain inlet.",
                "subject": "poseidon2",
                "relation": "domain",
                "obj": "inlet",
            },
        ]
    )
    assert continuation_text("and zeus2?", window, _Names()) == "what is the domain of zeus2"
    assert continuation_text("what is the domain of zeus2", window, _Names()) == (
        "what is the domain of zeus2"
    )


def test_fanout_abstains_without_residual_rows():
    choice = decision_fanout("which domain", ["sky", "sea"], {"state": {}})
    assert choice["probability"] == 0.0
    assert choice["answer"] == ""
    assert choice["evidence"] == []


def test_fanout_matches_a_residual_row():
    choice = decision_fanout(
        "domain",
        ["sky", "sea"],
        {"state": {"rows": [{"subject": "Zeus", "relation": "domain", "obj": "sky"}]}},
    )
    assert choice["answer"] == "sky"
    assert choice["probability"] >= 0.99
    assert choice["evidence"]


def test_cascade_abstains_without_rows_and_resolves_with_them():
    empty = CascadeRouter().route("domain", ["sky", "sea"], ControlPacket(id="empty").to_dict())
    assert empty["route"] == "escalate"
    assert empty["verify"]["verified"] is False

    packet = ControlPacket(id="rows").to_dict()
    packet["state"] = {"rows": [{"subject": "Zeus", "relation": "domain", "obj": "sky"}]}
    found = CascadeRouter().route("domain", ["sky", "sea"], packet)
    assert found["route"] == "residual"
    assert found["result"]["status"] == "ok"
    assert found["verify"]["verified"] is True


def test_chat_page_renders_companion_and_message_kinds():
    html = (ROOT / "landing" / "public" / "chat.html").read_text(encoding="utf-8")
    assert "message_kind" in html
    assert "companion_prompt" in html
    assert "tutorial_fragment" in html
    assert 'id="returning-companion"' in html
    assert "Stores · Derives · Abstains" in html
    assert "Sign in with a username" in html
    assert "shiftKey" in html
    assert 'href="/chat.html"' not in html
    redirects = ROOT / "landing" / "public" / "_redirects"
    if redirects.exists():
        assert "/chat.html" not in redirects.read_text(encoding="utf-8")


def test_history_follow_up_answers_from_the_store(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    hub = "h" + uuid.uuid4().hex[:10]
    left = "p" + uuid.uuid4().hex[:8]
    right = "z" + uuid.uuid4().hex[:8]
    for line, _name in (
        (f"remember {left} domain inlet", left),
        (f"remember {right} domain ridge", right),
    ):
        learned = client.post("/api/v1/chat", json={"message": line, "hub_id": hub})
        assert learned.status_code == 200, learned.text
        assert learned.json()["action_taken"]["wrote"] is True, learned.text
        assert learned.json()["cycle_verified"] is True

    bare = client.post(
        "/api/v1/chat",
        json={"message": f"and {right}?", "history": [], "hub_id": hub},
    )
    assert bare.status_code == 200, bare.text
    assert "ridge" not in (bare.json().get("rows") or [])

    followed = client.post(
        "/api/v1/chat",
        json={
            "message": f"and {right}?",
            "hub_id": hub,
            "history": [
                {"role": "user", "content": f"what is the domain of {left}"},
                {
                    "role": "assistant",
                    "content": f"{left} domain inlet.",
                    "subject": left,
                    "relation": "domain",
                    "obj": "inlet",
                },
            ],
        },
    )
    assert followed.status_code == 200, followed.text
    body = followed.json()
    assert body["history_used"] == 2
    assert body["hermes_budget"]["used"] == 2
    assert "ridge" in body["rows"]
    assert body["cycle_verified"] is True
    assert body["message_kind"] == "residual"
    assert "sea" not in body["reply_text"]


def test_verified_turn_speaks_and_unverified_turn_does_not_write(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    hub = "c" + uuid.uuid4().hex[:12]
    greeted = client.post(
        "/api/v1/chat",
        json={"text": "hello", "hub_id": hub, "persona": "honest"},
    )
    assert greeted.status_code == 200, greeted.text
    hello = greeted.json()
    assert hello["cycle_verified"] is True
    assert hello["mouth_open"] is True
    assert hello["message_kind"] == "mouth"
    assert "won't assert" in hello["reply_text"].lower()
    assert hello.get("companion_prompt")
    assert "Stores · Derives · Abstains" in hello["companion_prompt"]
    assert "username" in hello["companion_prompt"].lower()
    legions = hello.get("legions") or {}
    assert legions.get("calliope", {}).get("writes_residual") is False
    assert legions.get("ligeia", {}).get("writes_residual") is False

    taught = client.post(
        "/api/v1/chat",
        json={"text": "remember that I prefer cycle_tea_2a49", "hub_id": hub},
    )
    assert taught.status_code == 200, taught.text
    taught_body = taught.json()
    assert taught_body["action_taken"]["wrote"] is True
    assert taught_body["rows"] == ["cycle_tea_2a49"]
    assert taught_body.get("tutorial_fragment")
    assert app_module.titanos_singleton.ask_list("user:" + hub, "prefers") == ["cycle_tea_2a49"]

    before = app_module.titanos_singleton.stats()["facts"]
    liked = client.post(
        "/api/v1/chat",
        json={"text": "I like cyclequiet2a49", "hub_id": hub},
    )
    assert liked.status_code == 200, liked.text
    assert liked.json()["action_taken"]["wrote"] is False
    assert app_module.titanos_singleton.stats()["facts"] == before
    from resileos.kin.aphrodite import get_store

    assert get_store().get(hub).preferences["cyclequiet2a49"]["likes"] == 1

    def _no_hash(text: str) -> dict:
        del text
        return {"packet_hash": "", "topics": [], "address": {}}

    monkeypatch.setattr("resileos.chat.turn_cycle.turn_residual", _no_hash)
    blocked = client.post(
        "/api/v1/chat",
        json={"text": "remember that I prefer cycle_blocked_2a49", "hub_id": hub},
    )
    assert blocked.status_code == 200, blocked.text
    blocked_body = blocked.json()
    assert blocked_body["cycle_verified"] is False
    assert blocked_body["action_taken"]["wrote"] is False
    assert blocked_body["message_kind"] == "abstain"
    assert "nothing was stored" in blocked_body["reply_text"].lower()
    assert "cycle_blocked_2a49" not in app_module.titanos_singleton.ask_list(
        "user:" + hub, "prefers"
    )

    quiet = client.post(
        "/api/v1/chat",
        json={"text": "hello again", "hub_id": hub, "persona": "honest"},
    )
    assert quiet.status_code == 200, quiet.text
    quiet_body = quiet.json()
    assert quiet_body["cycle_verified"] is False
    assert quiet_body["mouth_open"] is False
    assert quiet_body["message_kind"] == "orientation"
    assert "invent" in quiet_body["reply_text"].lower()
    assert "i'm here" not in quiet_body["reply_text"].lower()
    assert "cycle_tea_2a49" not in quiet_body["reply_text"]
