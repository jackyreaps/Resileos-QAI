"""HTTP shapes for chat, the hub ledger, studio, and the UI routes."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def open_api(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)


def test_chat_is_closed_without_a_key(client):
    response = client.post(
        "/api/v1/chat",
        json={"text": "hello", "hub_id": "alice"},
    )
    if os.getenv("RESILEOS_AUTH_BYPASS") == "1":
        assert response.status_code == 200
        return
    assert response.status_code in (401, 403, 503)


def test_chat_five_outcomes_and_ledger(client, open_api):
    learned = client.post(
        "/api/v1/chat",
        json={
            "text": "remember that I prefer exact_answers",
            "hub_id": "stripuser",
            "persona": "honest",
        },
    )
    assert learned.status_code == 200, learned.text
    body = learned.json()
    assert body["router_class"] == "HUB_LEARN"
    assert body["status"] == "ACCEPTED"
    assert body["memory_chip"] is True
    assert body["chip"] is None
    assert body["subject"] == "user:stripuser"
    assert body["action_taken"]["wrote"] is True
    assert body["rows"] == ["exact_answers"]

    recalled = client.post(
        "/api/v1/chat",
        json={"text": "what do I prefer", "hub_id": "stripuser"},
    )
    assert recalled.status_code == 200
    recalled_body = recalled.json()
    assert recalled_body["router_class"] == "HUB_RECALL"
    assert recalled_body["rows"] == ["exact_answers"]
    assert recalled_body["status"] == "ACCEPTED"
    assert "sea" not in recalled_body["reply_text"]

    client.post(
        "/api/v1/learn",
        json={"subject": "Zeus", "relation": "domain", "obj": "sky"},
    )
    fact = client.post(
        "/api/v1/chat",
        json={"text": "what is the domain of Zeus", "hub_id": "stripuser"},
    )
    fact_body = fact.json()
    assert fact.status_code == 200
    assert fact_body["router_class"] == "TOOL_FACT"
    assert fact_body["status"] == "ACCEPTED"
    assert fact_body["chip"] is None
    assert fact_body["rows"] == ["sky"]
    assert "sea" not in fact_body["reply_text"]

    soft = client.post(
        "/api/v1/chat",
        json={"text": "hello", "hub_id": "stripuser", "persona": "honest"},
    )
    soft_body = soft.json()
    assert soft_body["router_class"] == "SOFT_CHAT"
    assert soft_body["action_taken"]["tool"] is None
    assert soft_body["cycle_verified"] is False
    assert soft_body["verified"] is False
    assert soft_body["source"] == "conversational"
    assert soft_body["mouth_open"] is True
    assert soft_body["message_kind"] == "mouth"
    assert soft_body["status"] == "ACCEPTED"
    assert "not a stored fact" in soft_body["reply_text"].lower()
    assert soft_body["factual_mouth"] is False
    assert "sky" not in soft_body["reply_text"]
    assert "exact_answers" not in soft_body["reply_text"]

    spoken = client.post(
        "/api/v1/chat",
        json={"text": "hello", "hub_id": "stripuser", "persona": "builder"},
    )
    spoken_body = spoken.json()
    assert spoken_body["status"] == "ACCEPTED"
    assert spoken_body["mouth_open"] is True
    assert spoken_body["verified"] is False
    assert "builder" in spoken_body["reply_text"].lower()
    assert spoken_body["reply_text"] != soft_body["reply_text"]
    assert "sky" not in spoken_body["reply_text"]

    abstain = client.post(
        "/api/v1/chat",
        json={
            "text": "and then?",
            "hub_id": "stripuser",
            "last_tool_empty": True,
        },
    )
    abstain_body = abstain.json()
    assert abstain_body["router_class"] == "ABSTAIN_SURFACE"
    assert abstain_body["status"] == "ABSTAINED"
    assert abstain_body["chip"] == "abstained"
    assert abstain_body["teach_affordance"] is True

    ledger = client.get("/api/v1/hub/stripuser/ledger")
    assert ledger.status_code == 200
    triples = ledger.json()["triples"]
    assert any(row["obj"] == "exact_answers" for row in triples)

    edited = client.put(
        "/api/v1/hub/stripuser/ledger",
        json={
            "relation": "prefers",
            "obj": "exact_answers",
            "new_obj": "short_answers",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["wrote"] is True

    missing = client.delete(
        "/api/v1/hub/stripuser/ledger",
        params={"relation": "prefers", "obj": "exact_answers"},
    )
    assert missing.status_code == 404

    deleted = client.delete(
        "/api/v1/hub/stripuser/ledger",
        params={"relation": "prefers", "obj": "short_answers"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["triples"] == [] or all(
        row["obj"] != "short_answers" for row in deleted.json()["triples"]
    )


def test_perception_does_not_write_until_eat_accepts(client, open_api, monkeypatch):
    import app as app_module
    from resileos.kin.eat import EatDecision
    from resileos.ui import routes as ui_routes

    before = app_module.titanos_singleton.stats()["facts"]
    image = [[0.0, 1.0], [1.0, 0.0]]
    held = client.post(
        "/api/v1/perceive/image",
        json={"image": image, "subject": "imgprobe", "commit": False},
    )
    assert held.status_code == 200, held.text
    assert held.json()["written"] == []
    assert held.json()["committed"] is False
    assert held.json()["candidates"]
    assert app_module.titanos_singleton.stats()["facts"] == before

    def _accept(claim, **kwargs):
        del kwargs
        return EatDecision(
            action="accept",
            subject=claim["subject"],
            relation=claim["relation"],
            obj=claim["obj"],
            reason="ok",
        )

    monkeypatch.setattr(ui_routes, "eat_filter", _accept)
    committed = client.post(
        "/api/v1/perceive/frame",
        json={"image": image, "subject": "frameprobe", "commit": True},
    )
    assert committed.status_code == 200, committed.text
    written = committed.json()["written"]
    assert written
    assert all(row["subject"] == "frameprobe" for row in written)
    assert app_module.titanos_singleton.ask_list("frameprobe", "residual_bin")


def test_agent_task_blocks_mutation_and_runs_reads(client, open_api):
    blocked = client.post(
        "/api/v1/agent/task",
        json={
            "goal": "do not write",
            "steps": [{"tool": "write_file", "args": {"rel": "nope.txt", "content": "x"}}],
        },
    )
    assert blocked.status_code == 200, blocked.text
    result = blocked.json()["result"]
    assert result["ran"] is False
    assert result["verification"]["requires_verification"] is True
    assert not (ROOT / "nope.txt").exists()

    read = client.post(
        "/api/v1/agent/task",
        json={"goal": "status", "steps": [{"tool": "git_status", "args": {}}]},
    )
    assert read.status_code == 200, read.text
    assert read.json()["result"]["ran"] is True


def test_language_mouth_explain_remember(client, open_api):
    detected = client.post("/api/v1/language/detect", json={"text": "hello world"})
    assert detected.status_code == 200
    assert detected.json()["guess"] == "latin"

    translated = client.post(
        "/api/v1/language/translate",
        json={"text": "hello", "target": "en"},
    )
    assert translated.status_code == 200
    assert translated.json()["translated"] == "hello"
    assert translated.json()["provider"] == "none"

    mouth = client.post(
        "/api/v1/mouth/custom",
        json={"rows": [{"subject": "Zeus", "relation": "domain", "obj": "sky"}], "question": ""},
    )
    assert mouth.status_code == 200
    assert mouth.json()["epistemic"] == "GROUNDED"
    assert "Zeus domain sky" in mouth.json()["text"]

    explained = client.post(
        "/api/v1/explain",
        json={"query": "domain", "hub_rows": ["sky"]},
    )
    assert explained.json()["source"] == "hub"

    remembered = client.post(
        "/api/v1/remember",
        json={"subject": "ada", "relation": "likes", "obj": "geometry"},
    )
    assert remembered.json()["subject"] == "user:ada"


def test_generate_routes(client, open_api):
    fluid = client.post("/api/v1/generate/fluid", json={"persona": "honest"})
    assert fluid.status_code == 200, fluid.text
    assert fluid.json()["still_url"]
    local = client.post("/api/v1/generate/local", json={"subject": "frame"})
    assert local.status_code == 200, local.text
    assert local.json()["pattern_shape"]


def test_studio_routes_and_sampler_refusal(client, open_api, monkeypatch):
    codecs = client.get("/api/v1/studio/codecs")
    assert codecs.status_code == 200
    assert "pca_component" in codecs.json()["codecs"]

    projected = client.post(
        "/api/v1/studio/codecs/project",
        json={"image": [[0, 1], [1, 0]], "m": 4, "n": 4},
    )
    assert projected.status_code == 200
    assert projected.json()["shape"] == [4, 4]

    candidate = client.post(
        "/api/v1/studio/candidates",
        json={"kind": "image", "path": "candidate://x", "title": "CANDIDATE"},
    )
    assert candidate.status_code == 200
    assert candidate.json()["learned"] is False
    assert candidate.json()["status"] == "candidate"

    prior = client.get("/api/v1/studio/service/prior")
    assert prior.status_code == 200
    assert "available" in prior.json()

    gate = client.post("/api/v1/studio/gate", json={"packet": {"version": "nope"}})
    assert gate.status_code == 200, gate.text
    assert gate.json()["well_formed"] is False
    assert gate.json()["learned"] is False

    panel = client.get("/api/v1/studio/panel")
    assert panel.status_code == 200
    assert panel.json()["http_invokes_renderer"] is False

    monkeypatch.delenv("RESILEOS_EXTERNAL_SAMPLER", raising=False)
    refused = client.post(
        "/api/v1/studio/external-sampler",
        json={"condition": {"prompt": "a quiet hill"}},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["refused"] is True

    monkeypatch.setenv("RESILEOS_EXTERNAL_SAMPLER", "fake")
    denied = client.post(
        "/api/v1/studio/external-sampler",
        json={"condition": {"prompt": "please delete the weights"}},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["risk"]["risk_class"] == "deny"

    allowed = client.post(
        "/api/v1/studio/external-sampler",
        json={"condition": {"prompt": "a quiet hill", "seed": 1}, "register": False},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["refused"] is False
    assert allowed.json()["learned"] is False


def test_studio_round_trip(client, open_api):
    response = client.post(
        "/api/v1/studio/service/round-trip",
        json={"image": [[0.1, 0.2], [0.3, 0.4]], "codec_name": "pca_component"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["learned"] is False
    assert body["scar_matrix_updated"] is False
    assert body["codec"] == "pca_component"

    missing = client.post(
        "/api/v1/studio/service/round-trip",
        json={"image": [[0, 1], [1, 0]], "codec_name": "learned_conv"},
    )
    assert missing.status_code == 409


def test_cors_defaults_and_preflight():
    from app import configured_cors_origins

    # The function reads the env at call time. The suite may have the var unset.
    origins = configured_cors_origins()
    if not os.getenv("RESILEOS_CORS_ORIGINS", "").strip():
        assert origins == [
            "https://resileosai.fun",
            "https://www.resileosai.fun",
        ]

    code = """
import os
os.environ.pop("RESILEOS_CORS_ORIGINS", None)
os.environ["RESILEOS_AUTH_BYPASS"] = "1"
from fastapi.testclient import TestClient
from asgi import app
client = TestClient(app)
response = client.options(
    "/api/v1/ready",
    headers={
        "Origin": "https://www.resileosai.fun",
        "Access-Control-Request-Method": "DELETE",
    },
)
assert response.status_code in (200, 204), response.status_code
assert response.headers.get("access-control-allow-origin") == "https://www.resileosai.fun"
allow = response.headers.get("access-control-allow-methods", "")
assert "DELETE" in allow
assert "PUT" in allow
print("ok")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT / 'scripts'}:{ROOT}"
    env.pop("RESILEOS_CORS_ORIGINS", None)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_cors_env_replaces_defaults(monkeypatch):
    monkeypatch.setenv("RESILEOS_CORS_ORIGINS", "https://example.test")
    from app import configured_cors_origins

    assert configured_cors_origins() == ["https://example.test"]
