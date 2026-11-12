"""Studio chat page contract and the message/text alias on POST /chat."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_chat_html_has_no_hardcoded_api_key():
    html = (ROOT / "landing" / "public" / "chat.html").read_text(encoding="utf-8")
    assert "const API_KEY" not in html
    assert "localStorage.getItem(" in html
    assert "resileos_api_key" in html
    assert "https://api.resileosai.fun/api/v1" in html
    assert "fonts.css" in html


def test_chat_page_signs_in_and_posts_studio_tools():
    html = (ROOT / "landing" / "public" / "chat.html").read_text(encoding="utf-8")
    assert 'id="portal"' in html
    assert 'id="portal-username"' in html
    assert "resileos_username" in html
    assert "resileos_theme" in html
    assert 'id="history-panel"' in html
    assert 'id="history-username"' in html
    assert 'id="input"' in html
    assert "<textarea" in html
    assert "shiftKey" in html
    assert "Remembers exactly" in html
    assert "Stores · Derives · Abstains" in html
    assert "/studio/forge/video" in html
    assert "/studio/graphify" in html
    assert "/studio/plan-test-debug" in html
    assert "/studio/stop" in html
    assert 'id="stop-run"' in html
    assert "eat_filter" in html
    assert "verify_on_stop" in html
    assert "UNAVAILABLE" in html
    assert "schedulePersist" in html
    assert "async function persistThread" in html
    assert "fonts.googleapis.com" not in html
    assert "superintelligence" not in html.lower()
    assert "RES-309" not in html
    assert 'href="/chat.html"' not in html
    sign_out = html.split("async function signOut()", 1)[1].split("['settings-url'", 1)[0]
    assert "resileos_username" in sign_out
    assert "resileos_api_key" not in sign_out
    assert "localStorage.clear" not in sign_out
    optional = html.split("function applyOptionalKey", 1)[1].split("function showApp", 1)[0]
    assert "if (!key) return;" in optional


def test_chat_accepts_message_alias(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    learned = client.post(
        "/api/v1/chat",
        json={"message": "remember alice works_at acme", "hub_id": "studio"},
    )
    assert learned.status_code == 200, learned.text
    body = learned.json()
    assert body["status"] == "ACCEPTED"
    assert body["value"]
    assert body["reply_text"] == body["value"]
    assert body["action_taken"]["wrote"] is True
    assert body["subject"] == "alice"

    asked = client.post(
        "/api/v1/chat",
        json={"message": "alice works_at", "hub_id": "studio"},
    )
    assert asked.status_code == 200, asked.text
    asked_body = asked.json()
    assert asked_body["status"] == "ACCEPTED"
    assert "acme" in asked_body["rows"]
    assert asked_body["verified"] is True

    unknown = client.post(
        "/api/v1/chat",
        json={"message": "alice unknown_relation_xyz", "hub_id": "studio"},
    )
    assert unknown.status_code == 200
    unknown_body = unknown.json()
    assert unknown_body["status"] in {"NO_ROWS", "ABSTAINED"}
    assert unknown_body["verified"] is False
    canned = "I am online and ready"
    assert canned not in (unknown_body.get("reply_text") or "")
    assert canned not in (unknown_body.get("value") or "")


def test_tools_post_unknown_is_404(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    missing = client.post("/api/v1/tools/definitely_missing_tool", json={})
    assert missing.status_code == 404

    residual = client.post("/api/v1/tools/residual_consistency", json={})
    assert residual.status_code == 200, residual.text
    payload = residual.json()
    assert payload["name"] == "residual_consistency"
    assert "result" in payload


def test_kin_cycle_accepts_json_body(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    response = client.post("/api/v1/kin/cycle", json={"apply_policy": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "report" in body
    assert "policy" in body
    assert "harness" in body


def test_hades_list_is_not_a_placeholder(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    response = client.get("/api/v1/kin/hades/list")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "checkpoints" in body
    assert isinstance(body["checkpoints"], list)
    assert body["checkpoints"] != [{"id": "cp_001", "name": "Initial verified state"}]

def test_video_generate_is_unavailable(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    response = client.post("/api/v1/tools/video_generate", json={"prompt": "demo"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "UNAVAILABLE"
    assert body.get("draft") is False
    dumped = str(body).lower()
    assert "example.com" not in dumped
    assert "http" not in dumped
