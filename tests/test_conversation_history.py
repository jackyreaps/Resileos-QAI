"""Conversation persistence: create, list, and get by username.

Threads are isolated by API key and by username. Auth stays required.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def conv_path(tmp_path, monkeypatch):
    path = tmp_path / "conversations.json"
    monkeypatch.setenv("RESILEOS_CONVERSATIONS_PATH", str(path))
    return path


def _auth_off(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv(
        "RESILEOS_API_KEYS",
        '{"conv-key":{"name":"conv","tier":"free","quota":50},'
        '"other-key":{"name":"other","tier":"free","quota":50}}',
    )


def _bypass(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)


def _thread(text: str, username: str = "ada", hub_id: str = "anon") -> dict:
    return {
        "username": username,
        "hub_id": hub_id,
        "messages": [
            {"role": "user", "text": text},
            {"role": "assistant", "text": "stored " + text},
        ],
    }


def test_auth_required_for_create_list_and_get(client, monkeypatch, conv_path):
    _auth_off(monkeypatch)
    missing = client.post("/api/v1/conversations", json=_thread("hello"))
    assert missing.status_code == 401
    listed = client.get("/api/v1/conversations", params={"username": "ada"})
    assert listed.status_code == 401
    fetched = client.get(
        "/api/v1/conversations/anything",
        params={"username": "ada"},
    )
    assert fetched.status_code == 401

    bad = client.post(
        "/api/v1/conversations",
        json=_thread("hello"),
        headers={"X-API-Key": "nope"},
    )
    assert bad.status_code == 403

    ok = client.post(
        "/api/v1/conversations",
        json=_thread("hello"),
        headers={"X-API-Key": "conv-key"},
    )
    assert ok.status_code == 200, ok.text
    assert conv_path.exists()


def test_create_list_get_and_update_by_username(client, monkeypatch, conv_path):
    _bypass(monkeypatch)
    headers = {"X-API-Key": "personal-key"}
    created = client.post(
        "/api/v1/conversations",
        json=_thread("remember zeus domain sky"),
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["username"] == "ada"
    assert body["hub_id"] == "anon"
    assert body["message_count"] == 2
    assert body["messages"][0]["text"] == "remember zeus domain sky"
    conversation_id = body["id"]

    listed = client.get(
        "/api/v1/conversations",
        params={"username": "ada", "hub_id": "anon"},
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()["conversations"]
    assert len(rows) == 1
    assert rows[0]["id"] == conversation_id
    assert "messages" not in rows[0]
    assert rows[0]["title"]

    fetched = client.get(
        f"/api/v1/conversations/{conversation_id}",
        params={"username": "ada", "hub_id": "anon"},
        headers=headers,
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["messages"][1]["text"] == "stored remember zeus domain sky"

    updated = client.put(
        f"/api/v1/conversations/{conversation_id}",
        json=_thread("a longer thread"),
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["messages"][0]["text"] == "a longer thread"
    again = client.get(
        f"/api/v1/conversations/{conversation_id}",
        params={"username": "ada"},
        headers=headers,
    )
    assert again.json()["message_count"] == 2
    assert again.json()["messages"][0]["text"] == "a longer thread"


def test_usernames_and_keys_are_isolated(client, monkeypatch, conv_path):
    _bypass(monkeypatch)
    ada_headers = {"X-API-Key": "shared-demo"}
    bob_headers = {"X-API-Key": "shared-demo"}
    other_headers = {"X-API-Key": "paid-key"}

    created = client.post(
        "/api/v1/conversations",
        json=_thread("ada only", username="ada"),
        headers=ada_headers,
    )
    assert created.status_code == 200, created.text
    conversation_id = created.json()["id"]

    bob_list = client.get(
        "/api/v1/conversations",
        params={"username": "bob"},
        headers=bob_headers,
    )
    assert bob_list.status_code == 200
    assert bob_list.json()["conversations"] == []

    bob_get = client.get(
        f"/api/v1/conversations/{conversation_id}",
        params={"username": "bob"},
        headers=bob_headers,
    )
    assert bob_get.status_code == 404

    other_get = client.get(
        f"/api/v1/conversations/{conversation_id}",
        params={"username": "ada"},
        headers=other_headers,
    )
    assert other_get.status_code == 404
    other_list = client.get(
        "/api/v1/conversations",
        params={"username": "ada"},
        headers=other_headers,
    )
    assert other_list.json()["conversations"] == []

    other_created = client.post(
        "/api/v1/conversations",
        json=_thread("paid copy", username="ada"),
        headers=other_headers,
    )
    assert other_created.status_code == 200
    ada_list = client.get(
        "/api/v1/conversations",
        params={"username": "ada"},
        headers=ada_headers,
    )
    ids = [row["id"] for row in ada_list.json()["conversations"]]
    assert ids == [conversation_id]


def test_hubs_do_not_share_a_username_list(client, monkeypatch, conv_path):
    _bypass(monkeypatch)
    headers = {"X-API-Key": "personal-key"}
    client.post(
        "/api/v1/conversations",
        json=_thread("in anon", hub_id="anon"),
        headers=headers,
    )
    client.post(
        "/api/v1/conversations",
        json=_thread("in world", hub_id="world:studio"),
        headers=headers,
    )
    anon = client.get(
        "/api/v1/conversations",
        params={"username": "ada", "hub_id": "anon"},
        headers=headers,
    )
    world = client.get(
        "/api/v1/conversations",
        params={"username": "ada", "hub_id": "world:studio"},
        headers=headers,
    )
    assert len(anon.json()["conversations"]) == 1
    assert len(world.json()["conversations"]) == 1
    assert anon.json()["conversations"][0]["title"] != world.json()["conversations"][0]["title"] or (
        anon.json()["conversations"][0]["id"] != world.json()["conversations"][0]["id"]
    )


def test_demo_key_username_cap_does_not_apply_to_personal_keys(client, monkeypatch, conv_path):
    _bypass(monkeypatch)
    monkeypatch.setenv("RESILEOS_DEMO_USER_CAP", "1")
    demo_key = "demo-shared-for-cap"
    digest = hashlib.sha256(demo_key.encode("utf-8")).hexdigest()
    monkeypatch.setenv("RESILEOS_DEMO_KEY_SHA256", digest)

    first = client.post(
        "/api/v1/conversations",
        json=_thread("one", username="ada"),
        headers={"X-API-Key": demo_key},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/conversations",
        json=_thread("two", username="bea"),
        headers={"X-API-Key": demo_key},
    )
    assert second.status_code == 429
    assert "1" in second.json()["detail"]

    again = client.post(
        "/api/v1/conversations",
        json=_thread("more from ada", username="ada"),
        headers={"X-API-Key": demo_key},
    )
    assert again.status_code == 200

    personal = client.post(
        "/api/v1/conversations",
        json=_thread("paid", username="bea"),
        headers={"X-API-Key": "a-paid-key"},
    )
    assert personal.status_code == 200, personal.text
    other_name = client.post(
        "/api/v1/conversations",
        json=_thread("paid two", username="cy"),
        headers={"X-API-Key": "a-paid-key"},
    )
    assert other_name.status_code == 200, other_name.text


def test_username_is_required_and_modest(client, monkeypatch, conv_path):
    _bypass(monkeypatch)
    headers = {"X-API-Key": "personal-key"}
    missing = client.post(
        "/api/v1/conversations",
        json={"messages": [{"role": "user", "text": "hi"}]},
        headers=headers,
    )
    assert missing.status_code == 422
    short = client.post(
        "/api/v1/conversations",
        json=_thread("hi", username="a"),
        headers=headers,
    )
    assert short.status_code == 400
    spaced = client.get(
        "/api/v1/conversations",
        params={"username": "not a name"},
        headers=headers,
    )
    assert spaced.status_code == 400


def test_public_site_links_chat_and_history_panel():
    index = (ROOT / "landing" / "public" / "index.html").read_text(encoding="utf-8")
    kin = (ROOT / "landing" / "public" / "kin.html").read_text(encoding="utf-8")
    chat = (ROOT / "landing" / "public" / "chat.html").read_text(encoding="utf-8")
    checkout = (
        ROOT / "landing" / "functions" / "api" / "create-checkout-session.js"
    ).read_text(encoding="utf-8")
    wrangler = (ROOT / "landing" / "wrangler.toml").read_text(encoding="utf-8")

    assert 'href="/chat"' in index
    assert 'href="/app"' not in index
    assert 'href="/chat.html"' not in index
    assert 'id="history-panel"' in chat
    assert 'id="history-username"' in chat
    assert "Shared demo key, rate-limited" in chat
    assert "const DEMO_API_KEY" in chat
    assert "/chat?checkout=success" in checkout
    assert "/chat?checkout=success" in wrangler
    assert "Eat stays Eat" in kin
