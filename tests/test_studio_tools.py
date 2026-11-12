"""Forge video, graphify ingest, and the plan/test/debug loop."""
from __future__ import annotations

import json
import stat
import sys
import uuid
from pathlib import Path

import pytest

from resileos.kin.eat import eat_filter as real_eat_filter
from resileos.kin.legions import kin_catalogue
from resileos.kin.moirai import reset_coordination
from resileos.kin.studio_tools import (
    run_forge_video,
    run_graphify,
    run_plan_test_debug,
)


@pytest.fixture(autouse=True)
def _desk():
    reset_coordination()
    yield
    reset_coordination()


def _names(kin: str) -> set[str]:
    return {row["name"] for row in kin_catalogue(kin)}


def test_forge_is_on_hermes_not_hades(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    from resileos.kin.studio_tools import register_studio_legions

    register_studio_legions()
    assert "forge_video" in _names("hermes")
    assert "forge_video" not in _names("hades")
    assert "graphify" in _names("eat")
    assert "graphify" not in _names("hermes")
    assert "plan_test_debug" in _names("hermes")


def test_forge_unavailable_without_a_provider(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    out = run_forge_video("a hill")
    assert out["status"] == "UNAVAILABLE"
    assert out["url"] is None
    assert out["draft"] is False
    assert out["patron"] == "hephaestus"
    dumped = json.dumps(out).lower()
    assert "http" not in dumped
    assert "example.com" not in dumped


def test_forge_uses_a_configured_provider_and_refuses_upscale_until_verified():
    calls = {"n": 0}

    def provider(prompt: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/clip.mp4", "prompt": prompt}

    refused = run_forge_video("hill", provider_fn=provider, stage="upscale")
    assert calls["n"] == 0
    assert refused["status"] == "refused"
    assert refused["url"] is None

    drafted = run_forge_video("hill", provider_fn=provider, stage="draft")
    assert calls["n"] == 1
    assert drafted["status"] == "submitted"
    assert drafted["url"] == "https://cdn.test/clip.mp4"
    assert drafted["draft"] is True

    empty = run_forge_video("hill", provider_fn=lambda prompt: {"job": "only"})
    assert empty["status"] == "UNAVAILABLE"
    assert empty["url"] is None

    upscaled = run_forge_video(
        "hill",
        provider_fn=provider,
        stage="upscale",
        verified=True,
        apollo_result={"success": True},
    )
    assert upscaled["status"] == "submitted"
    assert upscaled["url"] == "https://cdn.test/clip.mp4"
    assert upscaled["draft"] is False
    assert calls["n"] == 2


def test_forge_runs_an_executable_provider(monkeypatch, tmp_path):
    script = tmp_path / "video-hook.py"
    script.write_text(
        "#!" + sys.executable + "\n"
        "import json, sys\n"
        "json.dump({'url': 'https://cdn.test/from-hook.mp4', 'prompt': sys.argv[1]}, sys.stdout)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("RESILEOS_VIDEO_PROVIDER", str(script))
    out = run_forge_video("marble hill")
    assert out["status"] == "submitted"
    assert out["url"] == "https://cdn.test/from-hook.mp4"
    assert out.get("process_alive") is not True


def test_graphify_learns_only_accepted_commits(monkeypatch):
    seen: list = []

    def spy(claim, **kwargs):
        seen.append(claim)
        return real_eat_filter(claim, **kwargs)

    monkeypatch.setattr("resileos.kin.studio_tools.eat_filter", spy)
    learned: list = []

    def learn(subject: str, relation: str, obj: str) -> None:
        learned.append((subject, relation, obj))

    source = {
        "edges": [
            {"from": "Zeus", "relation": "domain", "to": "sky"},
            {"from": "sys:agency", "relation": "policy", "to": "open"},
        ],
        "note": "what is the meaning of life?",
    }
    text = "Zeus domain sky\nwhat is the meaning of life?\nsys:agency policy open"
    preview = run_graphify(text, commit=True, learn_fn=learn)
    assert preview["learned"] == 1
    assert learned == [("Zeus", "domain", "sky")]
    actions = {row["reason"]: row["action"] for row in preview["decisions"]}
    assert actions["ok"] == "accept"
    assert actions["unstructured_prose"] == "abstain"
    assert actions["sys_subject_forbidden"] == "reject"
    assert seen, "graphify bypassed eat_filter"

    learned.clear()
    skipped = run_graphify(source, commit=False, learn_fn=learn)
    assert learned == []
    assert skipped["learned"] == 0
    assert skipped["claims"] == []
    assert any(row["action"] == "accept" for row in skipped["decisions"])

    learned.clear()
    run_graphify(
        {"edges": [{"from": "Athena", "relation": "domain"}]},
        commit=True,
        learn_fn=learn,
        # skip_eat is not a gate; Eat still runs
    )
    # The call above used commit and a missing object, so nothing is learned.
    assert learned == []
    bypass = run_graphify(
        "Hera domain marriage",
        commit=True,
        learn_fn=learn,
    )
    assert ("Hera", "domain", "marriage") in learned
    assert bypass["learned"] == 1
    assert all("skip_eat" not in row for row in bypass["decisions"])


def test_graphify_ignores_a_skip_flag(monkeypatch):
    seen: list = []

    def spy(claim, **kwargs):
        seen.append(claim)
        kwargs.pop("skip_eat", None)
        return real_eat_filter(claim, **kwargs)

    monkeypatch.setattr("resileos.kin.studio_tools.eat_filter", spy)
    learned: list = []
    out = run_graphify(
        "Poseidon domain sea",
        commit=False,
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
    )
    assert seen
    assert learned == []
    assert out["claims"] == []


def test_plan_loop_makes_progress_and_does_not_get_stuck():
    state = {"n": 0}

    def test_fn(goal: str, rounds: int) -> dict:
        del goal, rounds
        state["n"] += 1
        if state["n"] == 1:
            return {"ok": False, "stdout": "LOWER-TIER-LEAK", "signature": "first"}
        return {"ok": True, "stdout": "LOWER-TIER-LEAK", "signature": "second"}

    out = run_plan_test_debug(
        "repair the joint",
        steps=[{"tool": "plan"}, {"tool": "test"}, {"tool": "debug"}],
        test_fn=test_fn,
        max_rounds=5,
    )
    assert out["progress"] is True
    assert out["stuck"] is False
    assert out["ok"] is True
    assert out["rounds"] <= 5
    assert out["checkpoint"] is None
    assert out["waited"] is False
    assert out["roles"]["hermes"] == "paths"
    assert out["roles"]["athena"] == "judgment"
    assert out["roles"]["themis"] == "law"
    assert out["roles"]["hades"] == "lessons"
    assert out["roles"]["momus"]["approved"] is False
    clean = json.dumps({"trace": out["trace"], "verified_step": out["verified_step"], "roles": out["roles"]})
    assert "LOWER-TIER-LEAK" not in clean
    assert "LOWER-TIER-LEAK" in json.dumps(out["lower_tier"])
    assert out["verified_step"]["verified"] is False
    assert out["verified_step"]["artefact"] == {"goal": "repair the joint", "verdict": "unverified"}

    def same(goal: str, rounds: int) -> dict:
        del goal, rounds
        return {"ok": False, "stdout": "SAME-LEAK", "signature": "same", "process_alive": True}

    stuck = run_plan_test_debug(
        "spin",
        steps=[{"tool": "test"}],
        test_fn=same,
        max_rounds=4,
    )
    assert stuck["stuck"] is True
    assert stuck["rounds"] == 2
    assert stuck["rounds"] <= 4
    assert stuck.get("process_alive") is not True
    assert stuck["lower_tier"][0]["waited"] is False
    assert stuck["waited"] is False
    assert "SAME-LEAK" not in json.dumps(stuck["verified_step"])


def test_plan_loop_keeps_lower_tier_out_of_a_verified_step(monkeypatch):
    captured: list = []

    class _Review:
        outcome = "need_more"
        verified = False
        reason = "critique only"

    def spy(*args, **kwargs):
        del kwargs
        captured.append(args[0])
        return _Review()

    monkeypatch.setattr("resileos.kin.demigods.checks.momus_review", spy)

    def test_fn(goal: str, rounds: int) -> dict:
        del goal, rounds
        return {"ok": True, "stdout": "LOWER-TIER-LEAK", "signature": "pass"}

    packet = {
        "verified": True,
        "scars": [],
        "evidence": [{"source": "probe", "result": {"matched": 1}}],
    }
    out = run_plan_test_debug(
        "prove the joint",
        steps=[{"tool": "test"}, {"tool": "debug"}],
        test_fn=test_fn,
        packet=packet,
        apollo_result={"success": True},
        spec={"requirements": []},
        residual_hash="ab" * 32,
        max_rounds=4,
    )
    assert out["verified_step"]["verified"] is True
    assert out["verified_step"]["artefact"]["verdict"] == "pass"
    assert "LOWER-TIER-LEAK" not in json.dumps(out["verified_step"])
    assert captured
    assert "LOWER-TIER-LEAK" not in json.dumps(captured[0])
    assert out["law_holds"] is True


def test_mutating_steps_stay_refused_until_verified():
    calls = {"n": 0}

    def write_file(**kwargs):
        calls["n"] += 1
        return {"ok": True, "rel": kwargs.get("rel")}

    steps = [
        {"tool": "plan"},
        {"tool": "write_file", "args": {"rel": "nope.txt", "content": "secret-write"}},
        {"tool": "test"},
    ]
    blocked = run_plan_test_debug(
        "edit",
        steps=steps,
        tools={"write_file": write_file},
        allow_mutate=True,
    )
    assert calls["n"] == 0
    refused = next(row for row in blocked["trace"] if row["tool"] == "write_file")
    assert refused["ran"] is False
    assert refused["reason"] == "refused until verified"
    assert "secret-write" not in json.dumps(blocked["verified_step"])

    scarred = run_plan_test_debug(
        "edit",
        steps=steps,
        tools={"write_file": write_file},
        allow_mutate=True,
        packet={"verified": True, "scars": ["open"], "evidence": []},
        apollo_result={"success": True},
    )
    assert calls["n"] == 0

    opened = run_plan_test_debug(
        "edit",
        steps=steps,
        tools={"write_file": write_file},
        allow_mutate=True,
        packet={
            "verified": True,
            "scars": [],
            "evidence": [{"source": "probe", "result": {"matched": 1}}],
        },
        apollo_result={"success": True},
    )
    assert calls["n"] == 1
    ran = next(row for row in opened["trace"] if row["tool"] == "write_file")
    assert ran["ran"] is True
    assert "secret-write" not in json.dumps(opened["verified_step"])
    assert "secret-write" not in json.dumps(opened["trace"])


def test_studio_http_routes(client, monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    before = app_module.titanos_singleton.stats()["facts"]

    video = client.post("/api/v1/studio/forge/video", json={"prompt": "a hill", "stage": "draft"})
    assert video.status_code == 200, video.text
    body = video.json()
    assert body["status"] == "UNAVAILABLE"
    assert body["url"] is None
    assert "http" not in json.dumps(body).lower()

    script = tmp_path / "video-hook.py"
    script.write_text(
        "#!" + sys.executable + "\n"
        "import json, sys\n"
        "json.dump({'url': 'https://cdn.test/route.mp4'}, sys.stdout)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("RESILEOS_VIDEO_PROVIDER", str(script))
    drafted = client.post("/api/v1/studio/forge/video", json={"prompt": "marble", "stage": "draft"})
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["status"] == "submitted"
    assert drafted.json()["url"] == "https://cdn.test/route.mp4"
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)

    subject = "g" + uuid.uuid4().hex[:8]
    abstained = client.post(
        "/api/v1/studio/graphify",
        json={"source": "what is the meaning of life?", "commit": True},
    )
    assert abstained.status_code == 200, abstained.text
    assert abstained.json()["learned"] == 0
    assert app_module.titanos_singleton.stats()["facts"] == before

    rejected = client.post(
        "/api/v1/studio/graphify",
        json={"source": "sys:agency policy open", "commit": True},
    )
    assert rejected.json()["decisions"][0]["action"] == "reject"
    assert app_module.titanos_singleton.stats()["facts"] == before

    preview = client.post(
        "/api/v1/studio/graphify",
        json={"source": f"{subject} domain sky", "commit": False},
    )
    assert preview.json()["decisions"][0]["action"] == "accept"
    assert preview.json()["claims"] == []
    assert app_module.titanos_singleton.stats()["facts"] == before

    committed = client.post(
        "/api/v1/studio/graphify",
        json={"source": f"{subject} domain sky", "commit": True},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["learned"] == 1
    assert app_module.titanos_singleton.stats()["facts"] == before + 1

    loop = client.post("/api/v1/studio/plan-test-debug", json={"goal": "check the loop"})
    assert loop.status_code == 200, loop.text
    loop_body = loop.json()
    assert loop_body["progress"] is True
    assert loop_body["stuck"] is False
    assert loop_body["verified_step"]["verified"] is False
    assert loop_body["checkpoint"] is None

    mutate = client.post(
        "/api/v1/studio/plan-test-debug",
        json={
            "goal": "do not write",
            "steps": [{"tool": "write_file", "args": {"rel": "nope.txt", "content": "x"}}],
        },
    )
    assert mutate.status_code == 200, mutate.text
    row = mutate.json()["trace"][0]
    assert row["tool"] == "write_file"
    assert row["ran"] is False
    assert row["refused"] is True
    assert not Path("nope.txt").exists()


def test_studio_ui_posts_the_three_routes():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src/resileos/ui/studio_app.py").read_text(encoding="utf-8")
    assert "/studio/forge/video" in text
    assert "/studio/graphify" in text
    assert "/studio/plan-test-debug" in text
    assert "not bundled" not in text.lower()
    assert "coming soon" not in text.lower()
    assert "Cerberus" not in text
