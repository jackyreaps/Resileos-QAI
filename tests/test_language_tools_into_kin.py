"""Language and Tools perceive actions reach into_kin. Eat still gates learn."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_studio_perceive_buttons_call_into_kin():
    text = (ROOT / "src" / "resileos" / "ui" / "studio_app.py").read_text(encoding="utf-8")
    for key in ("perc_text", "perc_a", "perc_v", "tool_perc_lang", "tool_perc_img"):
        start = text.index(f'key="{key}"')
        window = text[start:start + 600]
        assert "into_kin" in window, key
        assert "hand_perception_to_psyche" in window, key


def test_live_panels_post_language_perceive():
    ui = (ROOT / "ui.py").read_text(encoding="utf-8")
    assert 'st.button("Perceive language", key="run_lang")' in ui
    assert '"/perceive/language"' in ui
    chat = (ROOT / "landing" / "public" / "chat.html").read_text(encoding="utf-8")
    assert "Perceive language" in chat
    assert "'/perceive/language'" in chat
    assert "commit: false" in chat


def test_hand_perception_reaches_the_same_psyche_without_learning():
    from resileos.kin.psyche import Psyche
    from resileos.ui.perceive_language import into_kin, perceive_language
    from resileos.ui.studio_app import hand_perception_to_psyche

    session: dict = {}
    perceived = perceive_language("hello world", subject="note")
    with pytest.warns(DeprecationWarning, match="without review"):
        handed = hand_perception_to_psyche(perceived, into_kin, session)
    mind = session["psyche"]
    assert isinstance(mind, Psyche)
    assert mind.state["phase"] == 2.0
    assert mind.state["drives"]["endocrine"] == 2.0
    assert handed["perception"]["tokens"] == 2
    assert handed["kin"]["state"]["phase"] == 2.0
    assert handed["kin"]["rows"]
    assert "applied" not in handed["kin"]
    assert "learned" not in handed["kin"]

    again = hand_perception_to_psyche(
        perceive_language("one two three"), into_kin, session
    )
    assert session["psyche"] is mind
    assert mind.state["phase"] == 3.0
    assert again["kin"]["state"]["drives"]["endocrine"] == 3.0


def test_language_route_calls_into_kin_and_eat_gates_learn(client, monkeypatch):
    import app as app_module
    from resileos.kin.eat import EatDecision
    from resileos.kin.psyche import Psyche
    from resileos.ui import routes as ui_routes
    from resileos.ui.perceive_language import into_kin as real_into_kin

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    session: dict = {}
    monkeypatch.setattr(ui_routes, "_language_session", session)
    calls: list[dict] = []

    def _spy(perceived, psyche=None):
        calls.append(perceived)
        return real_into_kin(perceived, psyche=psyche)

    monkeypatch.setattr("resileos.ui.perceive_language.into_kin", _spy)
    before = app_module.titanos_singleton.stats()["facts"]
    learned: list[tuple[str, str, str]] = []
    real_learn = app_module.titanos_singleton.learn

    def _learn(subject, relation, obj, *args, **kwargs):
        learned.append((subject, relation, obj))
        return real_learn(subject, relation, obj, *args, **kwargs)

    monkeypatch.setattr(app_module.titanos_singleton, "learn", _learn)

    def _gate(claim, **kwargs):
        del kwargs
        relation = claim["relation"]
        if relation == "tokens":
            action = "accept"
        elif relation == "chars":
            action = "abstain"
        else:
            action = "reject"
        return EatDecision(
            action=action,
            subject=claim["subject"],
            relation=relation,
            obj=claim["obj"],
            reason=action,
        )

    monkeypatch.setattr(ui_routes, "eat_filter", _gate)
    held = client.post(
        "/api/v1/perceive/language",
        json={"text": "hello world", "subject": "langkin", "commit": False},
    )
    assert held.status_code == 200, held.text
    body = held.json()
    assert body["committed"] is False
    assert body["written"] == []
    assert body["perception"]["tokens"] == 2
    assert body["kin"]["state"]["phase"] == 2.0
    assert body["kin"]["state"]["drives"]["endocrine"] == 2.0
    assert "applied" not in body["kin"]
    assert calls and calls[-1]["subject"] == "langkin"
    assert isinstance(session.get("psyche"), Psyche)
    assert session["psyche"].state["phase"] == 2.0
    assert learned == []
    assert app_module.titanos_singleton.stats()["facts"] == before
    actions = {row["triple"]["relation"]: row["eat"]["action"] for row in body["candidates"]}
    assert actions["tokens"] == "accept"
    assert actions["chars"] == "abstain"
    assert actions["latin_share"] == "reject"

    committed = client.post(
        "/api/v1/perceive/language",
        json={"text": "hello world", "subject": "langkin", "commit": True},
    )
    assert committed.status_code == 200, committed.text
    written = committed.json()["written"]
    assert written == [{"subject": "langkin", "relation": "tokens", "obj": "2"}]
    assert committed.json()["committed"] is True
    assert learned == [("langkin", "tokens", "2")]
    assert app_module.titanos_singleton.ask_list("langkin", "tokens")
    assert not app_module.titanos_singleton.ask_list("langkin", "chars")
    assert not app_module.titanos_singleton.ask_list("langkin", "latin_share")
    assert not app_module.titanos_singleton.ask_list("user:mind", "phase")
    assert not app_module.titanos_singleton.ask_list("user:mind", "residual_bin")
    assert session["psyche"].state["phase"] == 2.0


def test_language_perceive_still_requires_api_key(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv(
        "RESILEOS_API_KEYS",
        '{"audit-key":{"name":"audit","tier":"free","quota":10}}',
    )
    closed = client.post(
        "/api/v1/perceive/language",
        json={"text": "hello", "subject": "text", "commit": False},
    )
    assert closed.status_code == 401
