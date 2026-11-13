"""Persona store: isolation, residual tiers, edit/delete, abstain."""
from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from resileos.persona.hook import persona_command_action, persona_hook
from resileos.persona.principal import (
    NotAMember,
    OptInRequired,
    PersonaError,
    PersonalFact,
    SecretRejected,
)
from resileos.persona.reflection import Openness, hub_frame, individual_frame
from resileos.persona.reflect import apply_turn_recall, recall_packet, reflect_utterance
from resileos.persona.seed import load_self_facts
from resileos.persona.store import (
    LANGUAGE_HUB_INTERFACE,
    PersonaStore,
    get_persona_store,
    guild_subject,
    set_persona_store,
)

ROOT = Path(__file__).resolve().parents[1]
SHARED = "Ask again when the row is missing."


@pytest.fixture
def store(tmp_path):
    held = PersonaStore(tmp_path / "persona")
    set_persona_store(held)
    yield held
    set_persona_store(None)


def _account(store: PersonaStore, account_id: str):
    from resileos.persona.principal import resolve_principal

    return resolve_principal(account_id=account_id)


def test_seed_needles_match_the_repo():
    seed = load_self_facts()
    assert seed.version >= 1
    seen = set()
    for row in (*seed.facts, *seed.tutorial):
        assert row["id"] not in seen
        seen.add(row["id"])
        path = ROOT / row["check"]
        assert path.is_file(), row["check"]
        assert row["needle"] in path.read_text(encoding="utf-8")
    ids = [row["id"] for row in seed.tutorial]
    assert ids[0] == "teach_fact"
    assert ids[-1] == "set_preference"


def test_package_does_not_call_titanos_or_residual_core():
    hub_source = (ROOT / "src" / "resileos" / "latent_hub.py").read_text(encoding="utf-8")
    assert LANGUAGE_HUB_INTERFACE == ("encode", "bind_bundle", "put", "get", "nearest")
    for name in LANGUAGE_HUB_INTERFACE:
        assert f"def {name}(" in hub_source
    for path in (ROOT / "src" / "resileos" / "persona").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                assert all("titanos" not in name and "latent_hub" not in name for name in names)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "titanos" not in node.module
                assert "latent_hub" not in node.module
                assert not node.module.endswith("core")


def test_individual_isolation_edit_and_delete(store: PersonaStore):
    alice = _account(store, "alice")
    bob = _account(store, "bob")
    store.put_stated(alice, "name", "Ada", kind="name")
    edited = store.put_stated(alice, "goal", "learn abstain", kind="goal")
    again = store.put_stated(alice, "goal", "learn exact recall", kind="goal")
    assert again["stated_at"] == edited["stated_at"]
    assert again["text"] == "learn exact recall"
    assert again["label"] == "user-stated"
    assert again["source"] == "user-stated"

    alice_text = " ".join(cell["text"] for cell in store.list_stated(alice))
    bob_text = " ".join(cell["text"] for cell in store.list_stated(bob))
    assert "Ada" in alice_text
    assert "Ada" not in bob_text
    bob_file = store.root / "individuals" / "account" / "bob.json"
    if bob_file.exists():
        assert "Ada" not in bob_file.read_text(encoding="utf-8")

    assert store.delete_stated(alice, "name") is True
    assert store.delete_stated(alice, "name") is False
    remaining = {cell["id"] for cell in store.list_stated(alice)}
    assert remaining == {"goal"}
    assert store.writes_titanos is False
    assert store.writes_latent_hub is False
    assert store.writes_residual_core is False


def test_unknown_user_fact_abstains(store: PersonaStore):
    answer = reflect_utterance("what is my name", "alice")
    assert answer is not None
    assert answer["status"] == "ABSTAINED"
    assert answer["known"] is False
    assert answer["label"] == "user-stated"
    assert "Ada" not in answer["text"]
    assert "user-stated" in answer["text"]

    store.put_stated(_account(store, "alice"), "name", "Ada", kind="name")
    known = reflect_utterance("what is my name", "alice")
    assert known["known"] is True
    assert "Ada" in known["text"]
    assert "not a verified fact" in known["text"]
    assert known["label"] == "user-stated"


def test_residual_drops_text_already_on_the_latent_seed(store: PersonaStore):
    seed = store.seed().latent_frame()["abstain"]
    alice = _account(store, "alice")
    store.put_stated(alice, "abstain", seed["text"], kind="stated")
    residual_ids = {cell["id"] for cell in store.list_residual(alice)}
    assert "abstain" not in residual_ids
    assert any(cell["id"] == "abstain" for cell in store.list_stated(alice))

    store.put_stated(alice, "name", "Ada", kind="name")
    residual_ids = {cell["id"] for cell in store.list_residual(alice)}
    assert "name" in residual_ids


def test_promotion_is_opt_in_and_personal_facts_stay_off_latent(store: PersonaStore):
    alice = _account(store, "alice")
    bob = _account(store, "bob")
    carol = _account(store, "carol")
    store.seat_member("demo", "ada", "alice", rank="steward")
    store.seat_member("demo", "bo", "bob", rank="member")
    assert guild_subject("demo") == "org:guild:demo"

    store.put_stated(alice, "name", "Ada", kind="name")
    store.put_stated(bob, "name", "Ada", kind="name")
    with pytest.raises(OptInRequired):
        store.promote_to_hub(alice, "demo", "name", opt_in=False)
    hub_before = store.read_hub("demo", alice)
    assert all(cell["id"] != "name" for cell in hub_before["residual"])

    store.promote_to_hub(alice, "demo", "name", opt_in=True)
    hub = store.read_hub("demo", bob)
    assert any(cell["id"] == "name" and cell["label"] == "hub-shared" for cell in hub["residual"])
    assert hub["frame"]["scores_beliefs"] is False
    dumped = str(hub)
    assert "carol" not in dumped
    with pytest.raises(NotAMember):
        store.read_hub("demo", carol)

    with pytest.raises(PersonalFact):
        store.promote_to_latent(alice, "demo", "name", opt_in=True)
    latent = " ".join(row["text"] for row in store.read_latent("all"))
    assert "Ada" not in latent
    assert all(row["label"] != "user-stated" for row in store.read_latent("all"))

    store.put_stated(alice, "practice", SHARED, kind="shared", personal=False)
    store.put_stated(bob, "practice", SHARED, kind="shared", personal=False)
    with pytest.raises(NotAMember):
        store.promote_to_latent(carol, "demo", "practice", opt_in=True)
    store.promote_to_hub(alice, "demo", "practice", opt_in=True)
    with pytest.raises(PersonaError):
        store.promote_to_latent(bob, "demo", "practice", opt_in=True)

    lifted = store.promote_to_latent(alice, "demo", "practice", opt_in=True)
    assert lifted["reflection"]["gnosis"] == "unfilled"
    assert lifted["reflection"]["recurring"] is True
    promoted = store.read_latent("promoted")
    assert any(row["text"] == SHARED and row["label"] == "latent-promoted" for row in promoted)
    assert "Ada" not in " ".join(row["text"] for row in store.latent_hub().read("all"))
    carol_stated = " ".join(cell["text"] for cell in store.list_stated(carol))
    assert SHARED not in carol_stated
    assert "Ada" not in carol_stated
    hub_after = store.read_hub("demo", alice)
    assert all(cell["id"] != "practice" for cell in hub_after["residual"])
    assert any(cell["id"] == "practice" for cell in store.list_stated(alice))


def test_session_memory_expires(tmp_path):
    moment = {"at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    held = PersonaStore(tmp_path / "session", clock=lambda: moment["at"], session_ttl_s=60)
    set_persona_store(held)
    try:
        from resileos.persona.principal import resolve_principal

        who = resolve_principal(session_id="trial")
        held.put_stated(who, "name", "Ada", kind="name")
        assert held.list_stated(who)
        moment["at"] = moment["at"] + timedelta(seconds=120)
        assert held.list_stated(who) == []
        assert reflect_utterance("what is my name", "trial")["status"] == "ABSTAINED"
    finally:
        set_persona_store(None)


def test_secrets_are_rejected(store: PersonaStore):
    alice = _account(store, "alice")
    with pytest.raises(SecretRejected):
        store.put_stated(alice, "note", "sk-abcdefghij123456", kind="stated")
    with pytest.raises(SecretRejected):
        store.put_stated(alice, "note", "api_key hunter2", kind="stated")
    assert store.list_stated(alice) == []


def test_mouth_and_tutorial_read_the_store(store: PersonaStore):
    from resileos.chat.persona_mouth import render_persona_mouth

    rendered = render_persona_mouth(
        status="ACCEPTED",
        persona="honest",
        subject="Zeus",
        relation="domain",
        rows=["sky"],
        router_class="TOOL_FACT",
        verified=True,
        prose=True,
        hub_id="alice",
    )
    recall = rendered["persona_recall"]
    assert recall["tier"] == "individual"
    assert recall["writes_titanos"] is False
    assert recall["writes_residual_core"] is False
    assert recall["gnosis"] == "unfilled"
    assert any(row["id"] == "stores-facts" and row["label"] == "verified-seed" for row in recall["self"])
    assert recall["tutorial"]["next"]["id"] == "teach_fact"
    assert "sky" in rendered["text"]

    body = {
        "hub_id": "alice",
        "reply_text": "I am here with you.",
        "value": "I am here with you.",
        "status": "ACCEPTED",
        "factual_mouth": False,
    }
    apply_turn_recall(body, "hello")
    assert "with you" in body["reply_text"]
    assert body["persona_recall"]["flow"] == ["individual", "hub", "latent"]

    ask = {
        "hub_id": "alice",
        "reply_text": "old",
        "value": "old",
        "status": "ACCEPTED",
        "factual_mouth": False,
    }
    apply_turn_recall(ask, "what is my name")
    assert ask["status"] == "ABSTAINED"
    assert "Ada" not in ask["reply_text"]

    store.record_tutorial(_account(store, "alice"), "teach_fact")
    packet = recall_packet("alice")
    assert "teach_fact" in packet["tutorial"]["completed"]
    assert packet["tutorial"]["next"]["id"] == "recall_fact"
    assert packet["user"][0]["label"] == "user-stated"


def test_persona_command_does_not_mark_a_write(store: PersonaStore):
    reply, status, action = persona_command_action("persona: name Ada", "alice")
    assert status == "ACCEPTED"
    assert action["wrote"] is False
    assert "user-stated" in reply
    anon_reply, anon_status, anon_action = persona_command_action("persona: name Nia", "anon")
    assert anon_status == "ABSTAINED"
    assert anon_action["wrote"] is False
    assert "Nia" not in " ".join(cell["text"] for cell in store.list_stated(_account(store, "alice")))
    listed = persona_hook("list", account_id="alice")
    assert listed["writes_titanos"] is False
    assert any(cell["text"] == "Ada" for cell in listed["stated"])


def test_http_isolation_edit_and_delete(store: PersonaStore):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from resileos.persona.routes import register_persona_routes

    app = FastAPI()
    register_persona_routes(app, auth_dep=None)
    client = TestClient(app)

    created = client.put(
        "/api/v1/persona/individual/name",
        params={"account_id": "alice"},
        json={"text": "Ada", "kind": "name"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["fact"]["label"] == "user-stated"
    assert created.json()["writes_titanos"] is False

    edited = client.put(
        "/api/v1/persona/individual/name",
        params={"account_id": "alice"},
        headers={"X-Resileos-Account": "alice"},
        json={"text": "Ada Lovelace", "kind": "name"},
    )
    assert edited.status_code == 200
    mismatch = client.get(
        "/api/v1/persona/individual",
        params={"account_id": "alice"},
        headers={"X-Resileos-Account": "bob"},
    )
    assert mismatch.status_code == 403

    bob = client.get("/api/v1/persona/individual", params={"account_id": "bob"})
    assert bob.status_code == 200
    assert bob.json()["stated"] == []
    assert "Ada" not in bob.text

    removed = client.delete(
        "/api/v1/persona/individual/name",
        params={"account_id": "alice"},
    )
    assert removed.status_code == 200
    gone = client.get("/api/v1/persona/individual", params={"account_id": "alice"})
    assert gone.json()["stated"] == []

    seed = client.get("/api/v1/persona/self")
    assert seed.status_code == 200
    assert seed.json()["version"] >= 1
    assert "Ada" not in seed.text


def test_frames_keep_properties_apart_and_collapse_abstains(store: PersonaStore):
    root = store.reflection.root.self_check()
    own = root["frame"]
    assert own["name"] == "meta-aware-root"
    assert own["dimensionality"] == len(own["axes"]) == 5
    assert own["level"] == 0
    assert own["openness"]["open"] is True
    assert own["genealogy"]
    assert root["recognized"]["is_frame"] is True
    assert root["failure"] is False
    assert root["abstain"]["status"] == "ABSTAINED"
    assert root["abstain"]["failure"] is False
    assert root["scores_beliefs"] is False
    assert root["collapse"]["refused"] is False
    for key in ("score", "rank", "belief_score", "truth"):
        assert key not in own

    alice = _account(store, "alice")
    stored = store.load_individual(alice).frame
    assert stored["tier"] == "individual"
    assert set(stored["axes"]) == {"statement", "source", "limit"}
    assert stored["dimensionality"] == 3
    assert stored["level"] == 3
    assert "abstain" in stored["verdict_space"]
    assert stored["scope"]
    assert stored["non_claims"]
    assert stored["scores_beliefs"] is False
    packet = recall_packet("alice")
    assert packet["frame"]["axes"] == stored["axes"]
    assert "dimensionality" in packet["frame"] and "level" in packet["frame"]
    wider = replace(hub_frame("demo"), axes=hub_frame("demo").axes + ("extra",))
    wider_gate = store.reflection.gate(individual_frame("alice"), wider)
    assert wider_gate["abstain"] is False
    assert wider_gate["scores_beliefs"] is False
    assert "truer" not in wider_gate
    assert (
        wider_gate["collapse"]["dimensionality"]["proposed"]
        > wider_gate["collapse"]["dimensionality"]["lower"]
    )

    store.seat_member("demo", "ada", "alice", rank="steward")
    store.put_stated(alice, "note", "Keep the axes apart.", kind="shared", personal=False)
    before = [cell["id"] for cell in store.read_hub("demo", alice)["residual"]]

    merged = replace(hub_frame("demo"), axes=("statement",))
    refused = store.promote_to_hub(alice, "demo", "note", opt_in=True, proposed=merged)
    assert refused["stored"] is False
    assert refused["status"] == "ABSTAINED"
    assert refused["failure"] is False
    assert refused["reflection"]["collapse"]["reason"] == "axes merged without a stated reason"
    assert "note" not in [cell["id"] for cell in store.read_hub("demo", alice)["residual"]]

    dropped = replace(hub_frame("demo"), non_claims=("does not rank users",))
    refused = store.promote_to_hub(alice, "demo", "note", opt_in=True, proposed=dropped)
    assert refused["status"] == "ABSTAINED"
    assert refused["failure"] is False
    assert "non-claims" in refused["reason"]
    assert "note" not in [cell["id"] for cell in store.read_hub("demo", alice)["residual"]]

    closed = replace(hub_frame("demo"), openness=Openness(open=False, how="sealed"))
    refused = store.promote_to_hub(alice, "demo", "note", opt_in=True, proposed=closed)
    assert refused["status"] == "ABSTAINED"
    assert refused["failure"] is False
    assert refused["reflection"]["collapse"]["closed_an_open_frame"] is True
    assert [cell["id"] for cell in store.read_hub("demo", alice)["residual"]] == before

    allowed = store.promote_to_hub(
        alice,
        "demo",
        "note",
        opt_in=True,
        proposed=merged,
        axis_merge_reason="the tutorial keeps only the statement axis",
    )
    assert allowed["stored"] is True
    assert allowed["failure"] is False
    assert allowed["reflection"]["collapse"]["refused"] is False
    assert allowed["frame"]["dimensionality"] == 1
    assert allowed["frame"]["scores_beliefs"] is False


def test_app_wires_persona_routes():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "register_persona_routes" in text
    assert get_persona_store is not None
