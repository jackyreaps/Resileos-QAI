"""Persona mouth: verified prose, abstain, lessons, and frame labels."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from resileos.chat.persona_envelope import build_envelope
from resileos.chat.persona_mouth import (
    budgeted_lessons,
    remember_verified_learn,
    render_persona_mouth,
    unsupported_tokens,
)
from resileos.kin.aphrodite import AphroditeStore, get_store, set_store
from resileos.kin.hades import Hades
from resileos.kin.mouth_policy import should_render_prose

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_mouth(tmp_path, monkeypatch):
    from resileos.kin.aphrodite import _STORE
    from resileos.kin.wiring import get_kin_bundle

    previous_store = _STORE
    bundle = get_kin_bundle()
    previous_hades = getattr(bundle, "_hades", None)
    bundle._hades = Hades(tmp_path / "hades")
    set_store(AphroditeStore(tmp_path / "aphrodite"))
    monkeypatch.setattr("resileos.chat.persona_mouth._hades_store", lambda: bundle._hades)
    try:
        yield bundle
    finally:
        set_store(previous_store)
        bundle._hades = previous_hades


def test_should_render_prose_rejects_a_closed_request():
    assert should_render_prose(False, require_verified=True) is False


def test_verified_fact_is_natural_language_and_only_the_stored_fact():
    rendered = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="Zeus",
        relation="domain",
        rows=["sky"],
        router_class="TOOL_FACT",
        verified=True,
        prose=True,
        prior_reply="Zeus domain sky.",
    )
    text = rendered["text"]
    assert rendered["apply"] is True
    assert rendered["factual"] is True
    assert "on record" in text.lower()
    assert "Zeus" in text and "domain" in text and "sky" in text
    assert "sea" not in text.lower()
    assert "king" not in text.lower()
    assert unsupported_tokens(text, ["Zeus", "domain", "sky"]) == []
    assert rendered["audit"]["backend"] == "structured"
    assert rendered["audit"]["epistemic"] == "GROUNDED"
    assert rendered["audit"]["codex"]
    assert rendered["audit"]["envelope"]["honesty"] > rendered["audit"]["envelope"]["fluency"]
    assert rendered["audit"]["envelope"]["honesty"] > rendered["audit"]["envelope"]["charm"]
    assert rendered["audit"]["envelope"]["writes_residual"] is False
    assert rendered["structured"]["rows"] == ["sky"]
    assert rendered["structured"]["value"] == "Zeus domain sky."


def test_abstain_and_conflict_do_not_pick_a_value():
    abstained = render_persona_mouth(
        status="ABSTAINED",
        persona="guide",
        subject="Nobody",
        relation="domain",
        rows=[],
        router_class="TOOL_FACT",
        verified=True,
        prose=True,
    )
    assert abstained["factual"] is False
    assert "sky" not in abstained["text"].lower()
    assert "sea" not in abstained["text"].lower()
    assert "remember that" in abstained["text"].lower()
    assert "do not have a verified fact" in abstained["text"].lower()

    conflict = render_persona_mouth(
        status="CONFLICT",
        persona="honest",
        subject="Athens",
        relation="capital_of",
        rows=["Ottoman", "Greece"],
        router_class="TOOL_FACT",
        verified=True,
        prose=True,
    )
    text = conflict["text"]
    assert conflict["factual"] is False
    assert "Ottoman" in text and "Greece" in text
    assert "will not pick" in text.lower()
    assert "is Ottoman." not in text
    assert "sea" not in text.lower()
    assert unsupported_tokens(text, ["Athens", "capital_of", "Ottoman", "Greece"]) == []


def test_unverified_cycle_does_not_assert_a_fact():
    rendered = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="Zeus",
        relation="domain",
        rows=["sky"],
        router_class="TOOL_FACT",
        verified=False,
        allow_mouth=True,
        prose=True,
        prior_reply="Zeus domain sky.",
    )
    assert rendered["factual"] is False
    assert "on record" not in rendered["text"].lower()
    assert "sky" not in rendered["text"].lower()
    assert "checking the record" in rendered["text"].lower()
    assert rendered["structured"]["rows"] == ["sky"]

    closed = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="Zeus",
        relation="domain",
        rows=["sky"],
        router_class="TOOL_FACT",
        verified=True,
        prose=False,
        prior_reply="sky",
    )
    assert closed["apply"] is False
    assert closed["factual"] is False


def test_lesson_and_care_show_up_on_the_next_sentence(isolated_mouth):
    del isolated_mouth
    lesson = remember_verified_learn("cara", "user:cara", "prefers", "cycle_tea")
    assert lesson == "learned user:cara prefers cycle_tea under verification"
    state = get_store().get("cara")
    assert state.preferences["cycle_tea"]["weight"] > 0
    assert state.handle("Zeus domain sky", verified=True)["writes_residual"] is False
    window = budgeted_lessons("cara")
    assert window == [lesson]
    rendered = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="user:cara",
        relation="prefers",
        rows=["cycle_tea"],
        router_class="HUB_RECALL",
        verified=True,
        prose=True,
        lessons=window,
        hub_id="cara",
    )
    text = rendered["text"]
    assert "cycle_tea" in text
    assert "stored that under verification" in text.lower()
    assert "keeping care on cycle_tea" in text.lower()
    assert "sky" not in text.lower()
    assert unsupported_tokens(
        text,
        ["user:cara", "prefers", "cycle_tea", lesson],
    ) == []


def test_unfinished_frames_do_not_branch_and_finished_tags_only_label():
    plain = build_envelope("honest", hub_scope="user:cara")
    unfinished = build_envelope("honest", hub_scope="user:cara", frame_tag="stewardship")
    assert unfinished["frame_tag"] is None
    assert unfinished["branched"] is False
    assert unfinished["weights"] == plain["weights"]
    assert unfinished["weights"]["honesty"] > unfinished["weights"]["fluency"]
    assert unfinished["weights"]["honesty"] > unfinished["weights"]["charm"]

    labeled = build_envelope(
        "honest",
        hub_scope="user:cara",
        frame_tag="diagnostic",
        finished_frames={"diagnostic"},
    )
    assert labeled["frame_tag"] == "diagnostic"
    assert labeled["branched"] is False
    assert labeled["weights"]["honesty"] > labeled["weights"]["charm"]
    spoken = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="Zeus",
        relation="domain",
        rows=["sky"],
        router_class="TOOL_FACT",
        verified=True,
        prose=True,
        frame_tag="diagnostic",
        finished_frames={"diagnostic"},
    )
    unlabeled = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="Zeus",
        relation="domain",
        rows=["sky"],
        router_class="TOOL_FACT",
        verified=True,
        prose=True,
    )
    assert spoken["text"] == unlabeled["text"]
    assert "diagnostic" not in spoken["text"].lower()
    assert "steward" not in spoken["text"].lower()
    assert spoken["audit"]["envelope"]["frame_tag"] == "diagnostic"
    assert spoken["audit"]["envelope"]["branched"] is False


def test_chat_prose_follow_up_abstain_and_closed_mouth(client, monkeypatch, isolated_mouth):
    import app as app_module

    del isolated_mouth
    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    hub = "m" + uuid.uuid4().hex[:10]
    topic = "t" + uuid.uuid4().hex[:8]
    taught = client.post(
        "/api/v1/chat",
        json={"text": f"remember that I prefer {topic}", "hub_id": hub, "prose": True},
    )
    assert taught.status_code == 200, taught.text
    taught_body = taught.json()
    assert taught_body["action_taken"]["wrote"] is True
    assert taught_body["factual_mouth"] is True
    assert "verified and stored" in taught_body["reply_text"].lower()
    assert topic in taught_body["reply_text"]
    assert "sea" not in taught_body["reply_text"]
    assert taught_body["structured"]["rows"] == [topic]
    assert get_store().get(hub).preferences[topic]["weight"] > 0
    assert get_store().get(hub).handle("a fact")["writes_residual"] is False

    asked = client.post(
        "/api/v1/chat",
        json={"text": "what do I prefer", "hub_id": hub, "prose": True, "allow_mouth": False},
    )
    assert asked.status_code == 200, asked.text
    asked_body = asked.json()
    assert asked_body["factual_mouth"] is True
    assert topic in asked_body["reply_text"]
    assert "stored that under verification" in asked_body["reply_text"].lower()
    assert "keeping care" in asked_body["reply_text"].lower()
    assert asked_body["lessons"]
    assert all(item.startswith("learned ") for item in asked_body["lessons"])
    assert "evidence" not in " ".join(asked_body["lessons"]).lower()

    greeted = client.post(
        "/api/v1/chat",
        json={"text": "hello", "hub_id": hub, "persona": "mythic", "prose": True},
    )
    hello = greeted.json()
    assert hello["router_class"] == "SOFT_CHAT"
    assert hello["factual_mouth"] is False
    assert hello["verified"] is False
    assert "not a stored fact" in hello["reply_text"].lower()
    assert topic not in hello["reply_text"]

    missing = client.post(
        "/api/v1/chat",
        json={"text": "what is the domain of Nobodyzz", "hub_id": hub, "prose": True},
    )
    abstain = missing.json()
    assert abstain["status"] in {"NO_ROWS", "ABSTAINED"}
    assert abstain["factual_mouth"] is False
    assert topic not in abstain["reply_text"]
    assert "sky" not in abstain["reply_text"].lower()
    assert "remember that" in abstain["reply_text"].lower()

    quiet = client.post(
        "/api/v1/chat",
        json={"text": "what do I prefer", "hub_id": hub, "prose": False, "allow_mouth": True},
    )
    assert quiet.status_code == 200, quiet.text
    quiet_body = quiet.json()
    assert quiet_body["factual_mouth"] is False
    assert "on record" not in quiet_body["reply_text"].lower()
    assert "verified and stored" not in quiet_body["reply_text"].lower()
    assert quiet_body["rows"] == [topic]


def test_unverified_chat_does_not_speak_or_write_the_fact(client, monkeypatch, isolated_mouth):
    import app as app_module

    del isolated_mouth
    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    hub = "u" + uuid.uuid4().hex[:10]
    topic = "v" + uuid.uuid4().hex[:8]
    seeded = client.post(
        "/api/v1/chat",
        json={"text": f"remember {topic} domain inlet", "hub_id": hub},
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["action_taken"]["wrote"] is True

    def _no_hash(text: str) -> dict:
        del text
        return {"packet_hash": "", "topics": [], "address": {}}

    monkeypatch.setattr("resileos.chat.turn_cycle.turn_residual", _no_hash)
    before = app_module.titanos_singleton.stats()["facts"]
    blocked = client.post(
        "/api/v1/chat",
        json={
            "text": f"remember {topic} domain ridge",
            "hub_id": hub,
            "prose": True,
            "allow_mouth": True,
        },
    )
    assert blocked.json()["cycle_verified"] is False
    assert blocked.json()["action_taken"]["wrote"] is False
    assert blocked.json()["factual_mouth"] is False
    assert "ridge" not in blocked.json()["reply_text"].lower()
    assert app_module.titanos_singleton.stats()["facts"] == before

    asked = client.post(
        "/api/v1/chat",
        json={
            "text": f"what is the domain of {topic}",
            "hub_id": hub,
            "prose": True,
            "allow_mouth": True,
        },
    )
    body = asked.json()
    assert body["cycle_verified"] is False
    assert body["factual_mouth"] is False
    assert "on record" not in body["reply_text"].lower()
    assert "inlet" not in body["reply_text"].lower()
    assert body["structured"]["rows"] == ["inlet"]


def test_chat_page_requests_prose_and_folds_trace():
    html = (ROOT / "landing" / "public" / "chat.html").read_text(encoding="utf-8")
    assert "prose: true" in html
    assert "trace-fold" in html
    assert "Details" in html
    assert 'id="settings-persona"' in html
    index = (ROOT / "landing" / "public" / "index.html").read_text(encoding="utf-8")
    assert "render_persona_mouth" not in index
    redirects = ROOT / "landing" / "public" / "_redirects"
    if redirects.exists():
        assert "/chat.html" not in redirects.read_text(encoding="utf-8")
