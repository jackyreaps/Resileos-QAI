"""Routes that were implemented and not mounted."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_kuramoto_field_is_constructed():
    from resileos.ui.shared_state import init_shared

    shared = init_shared()
    assert shared["field"] is not None
    assert shared["field"].r == 3


def test_ui_console_wires_chat_ledger_and_studio():
    text = (ROOT / "ui.py").read_text(encoding="utf-8")
    assert 'st.set_page_config(page_title="Resileos"' in text
    assert '"/chat"' in text
    assert "HUB_LEARN" in text
    assert "/ledger" in text
    assert "render_residual_codec" in text
    assert "/aphrodite/" in text
    assert "/task/lookup" in text
    assert "/generate/video" in text
    assert "/perceive/audio" in text
    assert "/perceive/language" in text
    assert "DEMO_API_KEY" not in text
    assert "Cerberus" not in text


def test_perceive_audio_video_language_hold_writes(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    before = app_module.titanos_singleton.stats()["facts"]

    audio = client.post(
        "/api/v1/perceive/audio",
        json={"wave": [0.0, 0.25, 0.0, -0.25], "subject": "tone", "commit": False},
    )
    assert audio.status_code == 200, audio.text
    audio_body = audio.json()
    assert audio_body["written"] == []
    assert audio_body["committed"] is False
    assert audio_body["perception"]["subject"] == "tone"
    assert audio_body["candidates"]

    video = client.post(
        "/api/v1/perceive/video",
        json={
            "frames": [
                [[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], [[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]],
                [[[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]],
            ],
            "subject": "clip",
            "commit": False,
        },
    )
    assert video.status_code == 200, video.text
    assert video.json()["written"] == []
    assert video.json()["perception"]["frames"] == 2

    language = client.post(
        "/api/v1/perceive/language",
        json={"text": "hello world", "subject": "note", "commit": False},
    )
    assert language.status_code == 200, language.text
    assert language.json()["perception"]["tokens"] == 2
    assert language.json()["committed"] is False
    assert app_module.titanos_singleton.stats()["facts"] == before


def test_task_lookup_reads_the_store(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    learned = client.post(
        "/api/v1/learn",
        json={"subject": "Zeus", "relation": "domain", "obj": "sky"},
    )
    assert learned.status_code == 200, learned.text
    looked = client.post(
        "/api/v1/task/lookup",
        json={
            "goal": "domain of Zeus",
            "steps": [{"subject": "Zeus", "relation": "domain"}],
        },
    )
    assert looked.status_code == 200, looked.text
    body = looked.json()
    assert body["goal"] == "domain of Zeus"
    assert body["trace"][0]["status"] == "HIT"
    assert "scale" in body
    assert "write_file" not in looked.text


def test_generate_video_route_is_unavailable(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    response = client.post("/api/v1/generate/video", json={"prompt": "a hill"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "UNAVAILABLE"
    assert body["url"] is None
    assert body["draft"] is False
    dumped = str(body).lower()
    assert "example.com" not in dumped
    assert "http" not in dumped
