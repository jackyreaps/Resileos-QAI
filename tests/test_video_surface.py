"""Studio video page: sibling route, stages, and the Hades panel."""
from __future__ import annotations

import json

import numpy as np
import pytest

from resileos.studio.video_page import SECTIONS, VIDEO_HTML


def _edge() -> list[list[float]]:
    image = np.zeros((8, 8), dtype=np.float64)
    image[:, :4] = 0.2
    image[:, 4:] = 0.8
    return [image.tolist(), image.tolist(), image.tolist()]


def test_page_layout_is_one_surface_and_names_no_other_product():
    html = VIDEO_HTML
    assert SECTIONS == ("prompt", "stages", "hades", "output")
    positions = [html.index(f'id="{section}"') for section in SECTIONS]
    assert positions == sorted(positions)
    assert html.index("Draft") < html.index("Verify") < html.index("Upscale")
    assert 'id="upscale"' in html
    upscale = html.split('id="upscale"', 1)[1][:80]
    assert "disabled" in html.split("<button id=\"upscale\"", 1)[1].split(">", 1)[0]
    assert "does not generate video" in html
    assert "Mouth off" in html
    assert 'href="/assets/site.css"' in html
    assert 'href="/assets/chat-ui.css"' in html
    assert "btn-label" in html
    assert 'id="timeline"' in html
    assert 'id="cost-meter"' in html
    assert "Reused frames" in html
    assert "Frames that would need a generative call" in html
    assert ">Checkpoint<" in html
    assert "Run scene steps" in html
    lowered = html.lower()
    for name in (
        "higgsfield",
        "seedance",
        "comfyui",
        "kapwing",
        "vidful",
        "aifreevideo",
        "stable video",
        "grok imagine",
    ):
        assert name not in lowered
    assert upscale
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    studio = (root / "src/resileos/ui/studio_app.py").read_text(encoding="utf-8")
    assert '"Video"' in studio
    assert "render_video_page" in studio
    legions = (root / "docs/320-titanos/legions.md").read_text(encoding="utf-8")
    inventory = (root / "docs/320-titanos/component-inventory.md").read_text(encoding="utf-8")
    assert "does not generate video" in legions
    assert "clip_codec.py" in legions
    assert "clip_codec.py" in inventory
    assert "does not generate" in inventory
    redirects = root / "landing/public/_redirects"
    assert not redirects.exists()


def test_video_routes_draft_verify_and_restore(client, monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.setenv("RESILEOS_IRIS_JSONL", str(tmp_path / "iris.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_JSONL", str(tmp_path / "hades.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_DIR", str(tmp_path / "hades"))
    monkeypatch.setenv("RESILEOS_SCENE_DIR", str(tmp_path / "scene"))
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)

    page = client.get("/studio/video")
    assert page.status_code == 200
    assert "Draft" in page.text
    assert "disabled" in page.text

    bare = client.post("/api/v1/studio/video", json={"prompt": "a hill", "stage": "draft"})
    assert bare.status_code == 200, bare.text
    bare_body = bare.json()
    assert bare_body["status"] == "UNAVAILABLE"
    assert bare_body["url"] is None
    assert bare_body["sequence_verified"] is False

    frames = _edge()
    drafted = client.post(
        "/api/v1/studio/video",
        json={"prompt": "held edge", "stage": "draft", "frames": frames},
    )
    assert drafted.status_code == 200, drafted.text
    draft_body = drafted.json()
    assert draft_body["status"] == "drafted"
    assert draft_body["bits_per_frame"]["base"] == 96
    assert draft_body["bits_per_frame"]["mean_delta"] == pytest.approx(0.0)
    assert draft_body["cost"]["reused_frames"] == 2
    assert draft_body["cost"]["generative_frames"] == 0
    assert draft_body["upscale_enabled"] is False
    assert draft_body["preview"]

    verified = client.post(
        "/api/v1/studio/video",
        json={
            "prompt": "held edge",
            "stage": "verify",
            "frames": frames,
            "sequence": draft_body["sequence"],
            "context": [{"subject": "edge", "relation": "holds", "obj": "left"}],
        },
    )
    assert verified.status_code == 200, verified.text
    verified_body = verified.json()
    assert verified_body["sequence_verified"] is True
    assert verified_body["checks"]["consistency_score"] == pytest.approx(1.0)
    assert verified_body["upscale_enabled"] is True
    assert verified_body["mouth"] is True
    assert verified_body["candidate"]["learned"] is False
    assert verified_body["checkpoint_id"]

    closed = client.post(
        "/api/v1/studio/video",
        json={
            "prompt": "held edge",
            "stage": "upscale",
            "frames": frames,
            "sequence": draft_body["sequence"],
        },
    )
    assert closed.status_code == 200, closed.text
    closed_body = closed.json()
    assert closed_body["status"] == "not_required"
    assert closed_body["url"] is None

    restored = client.post(
        "/api/v1/studio/video/restore",
        json={"checkpoint_id": verified_body["checkpoint_id"]},
    )
    assert restored.status_code == 200, restored.text
    fresh = restored.json()
    assert fresh["fresh"]["verified"] is False
    assert fresh["residual_hash"] == verified_body["packet_hash"]
    assert "Ub" not in json.dumps(fresh)

    checkpoint = client.post(
        "/api/v1/studio/video/checkpoint",
        json={"prompt": "held edge", "frames": frames, "sequence": draft_body["sequence"]},
    )
    assert checkpoint.status_code == 200, checkpoint.text
    assert checkpoint.json()["status"] == "checkpoint"
    assert checkpoint.json()["verified"] is True

    scene = client.post(
        "/api/v1/studio/video/scene",
        json={"script": "UNIQUE_SCENE_SENTINEL labyrinth at dusk"},
    )
    assert scene.status_code == 200, scene.text
    scene_body = scene.json()
    assert scene_body["stub"] is True
    assert scene_body["url"] is None
    assert [step["legion"] for step in scene_body["steps"]] == ["daedalus", "helios", "argus"]
    assert "UNIQUE_SCENE_SENTINEL" not in json.dumps(scene_body)
