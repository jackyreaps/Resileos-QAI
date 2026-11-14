"""Admin Operator: control packet card and Hades controls (admin-only)."""
from pathlib import Path

import pytest

from test_proxy_identity import keys  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
OPS = {"X-API-Key": "ops-key"}


@pytest.fixture
def hades(tmp_path, monkeypatch):
    import app as app_module
    from resileos.harness.packet import ControlPacket
    from resileos.kin.hades import make_hades

    bundle, _ = app_module._hades_store()
    store = make_hades(tmp_path / "hades")
    monkeypatch.setattr(bundle, "_hades", store, raising=False)
    packet = ControlPacket(id="op-test")
    packet.append({"event": "draft"})
    monkeypatch.setattr(bundle, "control", packet, raising=False)
    return bundle, store


def test_operator_endpoints_refuse_plain_keys(client, keys, hades):  # noqa: F811
    for method, path in [("GET", "/api/v1/operator/state"), ("POST", "/api/v1/kin/hades/save"),
                         ("POST", "/api/v1/kin/hades/restore_latest_verified"), ("POST", "/api/v1/kin/hades/restart_lesson")]:
        assert client.request(method, path, json={}, headers={"X-API-Key": "user-key"}).status_code == 403, path


def test_save_restore_and_restart_from_lesson(client, keys, hades):  # noqa: F811
    bundle, store = hades
    state = client.get("/api/v1/operator/state", headers=OPS).json()
    assert state["control"]["id"] == "op-test" and state["control"]["events"] == ["draft"]
    assert client.post("/api/v1/kin/hades/restore_latest_verified", json={}, headers=OPS).status_code == 404
    bundle.control.verified = True
    bundle.control.scars.append("old mistake")
    saved = client.post("/api/v1/kin/hades/save", json={"lesson": "check the bounds first"}, headers=OPS).json()
    assert saved["status"] == "SAVED" and saved["verified"] is True
    back = client.post("/api/v1/kin/hades/restore_latest_verified", json={}, headers=OPS).json()
    assert back["checkpoint_id"] == saved["checkpoint_id"] and back["control"]["verified"] is False
    assert back["control"]["scars"] == 0
    fresh = client.post("/api/v1/kin/hades/restart_lesson", json={}, headers=OPS).json()
    assert fresh["control"]["guides_loaded"] == ["lesson:" + saved["checkpoint_id"]]
    assert fresh["control"]["events"] == [] and fresh["control"]["scars"] == 0
    assert bundle.control.guide_bodies["lesson:" + saved["checkpoint_id"]] == "check the bounds first"


def test_operator_page_and_chat_stream_client_are_wired():
    js = (ROOT / "landing" / "public" / "assets" / "admin.js").read_text()
    assert '["operator", "/admin/operator", "Operator"]' in js
    for text in ("Control packet", "Save checkpoint", "Restore latest verified", "Restart from lesson only",
                 "Evidence", "Writer proposed", "Reviewers (blind to the writer)", "Runs and replay"):
        assert text in js, text
    assert js.count("function replayCard()") == 1  # one replay, shared, not duplicated
    assert (ROOT / "landing" / "public" / "admin" / "operator.html").exists()
    chat = (ROOT / "landing" / "public" / "chat.html").read_text()
    assert '<script src="/assets/stream-parts.js"></script>' in chat
    assert "url: `${apiUrl()}/chat/stream`" in chat and "fallback: () => plainAssist(payload)" in chat
    assert "/chat/stream/${turn.streamId}/cancel" in chat and "Try again" in chat
    parts = (ROOT / "landing" / "public" / "assets" / "stream-parts.js").read_text()
    for plain in ('"Checked"', '"Not verified"', '"Searched"'):
        assert plain in parts
