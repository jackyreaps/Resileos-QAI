"""Verify, checkpoint, and upscale a temporal residual sequence."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from resileos.core import ResidualCore
from resileos.kin.legions import LegionError
from resileos.kin.moirai import reset_coordination
from resileos.kin.residual_trace import hades_path, iris_path, read_jsonl
from resileos.kin.studio_tools import run_forge_video
from resileos.studio.residual_cascade import VisualPathError
from resileos.studio.sequence_stage import restore_clip_checkpoint, run_sequence_stage


@pytest.fixture(autouse=True)
def _traces(monkeypatch, tmp_path):
    monkeypatch.setenv("RESILEOS_IRIS_JSONL", str(tmp_path / "iris.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_JSONL", str(tmp_path / "hades.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_DIR", str(tmp_path / "hades"))
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    monkeypatch.delenv("RESILEOS_UPSCALE_PROVIDER", raising=False)
    reset_coordination()
    yield
    reset_coordination()


def _edge() -> list[list[float]]:
    image = np.zeros((8, 8), dtype=np.float64)
    image[:, :4] = 0.2
    image[:, 4:] = 0.8
    return [image.tolist(), image.tolist(), image.tolist()]


def _checker() -> list[list[float]]:
    image = (np.indices((8, 8)).sum(axis=0) % 2).astype(np.float64)
    return [image.tolist(), image.tolist(), image.tolist()]


def test_verify_passes_and_reports_bits_and_consistency():
    secret = "super-secret-prompt-token"
    frames = _edge()
    drafted = run_sequence_stage(stage="draft", prompt=secret, frames=frames)
    assert drafted["status"] == "drafted"
    assert drafted["sequence_verified"] is False
    assert drafted["mouth"] is False
    assert drafted["candidate"] is None
    assert drafted["url"] is None
    assert drafted["hades_checkpoint"] is False
    assert drafted["bits_per_frame"]["base"] == 96
    assert drafted["bits_per_frame"]["deltas"] == []
    assert drafted["bits_per_frame"]["mean_delta"] == pytest.approx(0.0)
    assert drafted["bits_per_frame"]["reused_frames"] == 2
    assert drafted["bits_per_frame"]["generative_frames"] == 0
    assert drafted["cost"]["reused_frames"] == 2
    assert drafted["cost"]["generative_frames"] == 0
    assert drafted["dispositions"][1]["disposition"] == "residual-consistent, reuse previous packet"
    packet = drafted["video_packet"]
    assert packet["provider_stage"] == "draft"
    assert packet["keyframe_ids"] == [0]
    assert packet["scene_script_hash"] is None
    assert len(packet["frame_residuals"]) == 3
    assert packet["frame_residuals"][1] == packet["frame_residuals"][0]

    verified = run_sequence_stage(
        stage="verify",
        prompt=secret,
        frames=frames,
        sequence=json.loads(json.dumps(drafted["sequence"])),
        context=[{"subject": "edge", "relation": "holds", "obj": "left"}, "a note"],
    )
    assert verified["outcome"] == "verified"
    assert verified["sequence_verified"] is True
    assert verified["checks"]["hash_match"] is True
    assert verified["checks"]["residual_consistency"] is True
    assert verified["checks"]["consistency_score"] == pytest.approx(1.0)
    assert verified["checks"]["hephaestus"] is True
    assert verified["checks"]["apollo"] is True
    assert verified["checks"]["verify_on_stop"] is True
    assert verified["checks"]["themis"] is True
    assert verified["checks"]["energy_closed"] is True
    assert verified["mouth"] is True
    assert verified["candidate"]["learned"] is False
    assert verified["candidate"]["status"] == "candidate"
    assert verified["hades_checkpoint"] is True
    assert verified["checkpoint"]["verified"] is True
    assert verified["checkpoint"]["lesson"].startswith("verified=true")
    assert verified["checkpoint"]["residual_hash"] == verified["packet_hash"]
    assert verified["upscale_enabled"] is True
    assert verified["context_ranked"][0]["subject"] == "edge"
    assert verified["step_core"] is False
    assert verified["scar_matrix_updated"] is False
    assert verified["learned"] is False
    assert verified["produces_video"] is False
    ckpt = Path(os.environ["RESILEOS_HADES_DIR"]) / f"{verified['checkpoint_id']}.json"
    text = ckpt.read_text(encoding="utf-8")
    assert secret not in text
    assert "Ub" not in text
    assert "verified=true" in text
    assert verified["packet_hash"] in text
    fresh = restore_clip_checkpoint(verified["checkpoint_id"])
    assert fresh["fresh"]["verified"] is False
    assert fresh["lesson"].startswith("verified=true")
    assert fresh["residual_hash"] == verified["packet_hash"]
    assert "Ub" not in json.dumps(fresh)

    calls = {"n": 0}

    def provider(payload: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/should-not-run.mp4", "payload": payload}

    closed = run_sequence_stage(
        stage="upscale",
        prompt=secret,
        frames=frames,
        sequence=drafted["sequence"],
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert closed["status"] == "not_required"
    assert closed["url"] is None
    assert closed["provider_frames"] == 0
    for path in (iris_path(), hades_path()):
        rows = read_jsonl(path)
        assert rows
        assert secret not in path.read_text(encoding="utf-8")
        assert any(row["verify_result"] == "verified" and row["consistency_score"] == 1.0 for row in rows)
        assert any(row["checkpoint_id"] == verified["checkpoint_id"] for row in rows)


def test_prompt_only_draft_is_unavailable_and_does_not_call_a_provider():
    calls = {"n": 0}

    def provider(_payload: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/nope.mp4"}

    out = run_sequence_stage(stage="draft", prompt="a hill", provider_fn=provider)
    assert calls["n"] == 0
    assert out["status"] == "UNAVAILABLE"
    assert out["url"] is None
    assert out["draft"] is False
    assert out["sequence_verified"] is False
    assert out["mouth"] is False
    assert "http" not in json.dumps(out).lower()


def test_bad_hash_and_deny_risk_refuse_upscale():
    frames = _edge()
    drafted = run_sequence_stage(stage="draft", prompt="edge", frames=frames)
    bad = json.loads(json.dumps(drafted["sequence"]))
    bad["sequence_hash"] = "0" * 64
    rejected = run_sequence_stage(stage="verify", prompt="edge", frames=frames, sequence=bad)
    assert rejected["outcome"] == "rejected"
    assert rejected["checks"]["hash_match"] is False
    assert rejected["sequence_verified"] is False
    assert rejected["hades_checkpoint"] is False
    assert rejected["mouth"] is False
    assert rejected["candidate"] is None
    assert rejected["upscale_enabled"] is False

    calls = {"n": 0}

    def provider(payload: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/nope.mp4", "payload": payload}

    refused = run_sequence_stage(
        stage="upscale",
        prompt="delete the clip",
        frames=_checker(),
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert refused["status"] == "refused"
    assert refused["url"] is None
    assert refused["checks"]["risk_class"] == "deny"


def test_inconclusive_upscale_sends_only_failing_deltas():
    seen: list[dict] = []

    def provider(payload: str) -> dict:
        seen.append(json.loads(payload))
        return {"url": "https://cdn.test/delta.mp4"}

    opened = run_sequence_stage(
        stage="upscale",
        prompt="checker hold",
        frames=_checker(),
        provider_fn=provider,
    )
    assert opened["status"] == "submitted"
    assert opened["url"] == "https://cdn.test/delta.mp4"
    assert opened["produces_video"] is False
    assert opened["sequence_verified"] is False
    assert opened["candidate"] is None
    assert opened["provider_frames"] == 1
    assert opened["provider_cost"] < opened["full_duration_cost"]
    assert len(seen) == 1
    body = seen[0]
    assert body["kind"] == "residual_delta"
    assert body["full_clip"] is False
    assert body["n_frames"] == 1
    assert "prompt" not in body
    assert [item["index"] for item in body["frames"]] == [0]
    assert body["frames"][0]["motion"]["unit"] == "phase_step"
    delta = np.asarray(body["frames"][0]["delta"], dtype=np.float64).reshape(8, 8)
    assert np.allclose(delta, np.asarray(_checker()[0]), atol=1e-5)

    missing = run_sequence_stage(stage="upscale", prompt="checker hold", frames=_checker())
    assert missing["status"] == "UNAVAILABLE"
    assert missing["url"] is None
    assert missing["provider_frames"] == 1
    assert "http" not in json.dumps({k: v for k, v in missing.items() if k != "sequence"}).lower()


def test_learn_and_step_stay_off_and_traces_are_capped(monkeypatch):
    steps = {"n": 0}
    original = ResidualCore.step

    def _spy(self, *args, **kwargs):
        steps["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ResidualCore, "step", _spy)
    monkeypatch.setattr(ResidualCore, "_scar_update", lambda *a, **k: (_ for _ in ()).throw(AssertionError("scar")))
    learned: list = []

    def learn(*args: object) -> None:
        learned.append(args)

    frames = _edge()
    with pytest.raises(VisualPathError):
        run_sequence_stage(stage="draft", prompt="edge", frames=frames, learn=learn)
    with pytest.raises(VisualPathError):
        run_sequence_stage(stage="draft", prompt="edge", frames=frames, bypass_zeus=True)
    with pytest.raises(LegionError):
        run_forge_video("edge", frames=frames, clip=True, learn_fn=learn)
    assert learned == []

    verified = run_forge_video("edge", frames=frames, clip=True, stage="verify")
    assert steps["n"] == 0
    assert verified["sequence_verified"] is True
    assert verified["hades_checkpoint"] is True
    assert verified["verified"] is False
    assert verified["kin"] == "hermes"
    assert verified["checks"]["consistency_score"] == pytest.approx(1.0)
    assert verified["bits_per_frame"]["base"] == 96
    assert verified["bits_per_frame"]["mean_delta"] == pytest.approx(0.0)
    assert verified["bits_per_frame"]["reused_frames"] == 2

    pair = [np.zeros((8, 8)).tolist(), np.full((8, 8), 0.2).tolist()]
    legacy = run_forge_video("pan", frames=pair, stage="draft")
    assert "motion" in legacy
    assert legacy.get("version") != "studio-clip/1"

    monkeypatch.setenv("RESILEOS_RESIDUAL_TRACE_CAP_BYTES", "700")
    for _ in range(12):
        run_sequence_stage(stage="draft", prompt="edge", frames=frames)
    for path in (iris_path(), hades_path()):
        raw = path.read_bytes()
        assert len(raw) <= 700
        rows = read_jsonl(path)
        assert rows
        assert rows[-1]["stage"] == "draft"
        assert "prompt" not in rows[-1]


def test_sigma_gate_makes_no_provider_call_and_ignores_a_stale_mouth():
    from types import SimpleNamespace

    from resileos.kin.wiring import get_kin_bundle

    calls = {"n": 0}

    def provider(payload):
        calls["n"] += 1
        return {"url": "https://cdn.test/should-not-run"}

    bundle = get_kin_bundle()
    previous = bundle.last_policy
    bundle.last_policy = SimpleNamespace(allow_mouth=False)
    try:
        drafted = run_sequence_stage(stage="draft", prompt="held edge", frames=_edge())
        assert drafted["mouth"] is False
        assert drafted["provider_called"] is False
        verified = run_sequence_stage(
            stage="verify",
            prompt="held edge",
            frames=_edge(),
            sequence=drafted["sequence"],
        )
        assert verified["mouth"] is True
        assert verified["sequence_verified"] is True
        upscaled = run_sequence_stage(
            stage="upscale",
            prompt="held edge",
            frames=_edge(),
            sequence=drafted["sequence"],
            provider_fn=provider,
        )
    finally:
        bundle.last_policy = previous
    assert calls["n"] == 0
    assert upscaled["provider_called"] is False
    assert upscaled["url"] is None
    assert upscaled["status"] == "not_required"
    assert upscaled["cost"]["generative_frames"] == 0
    assert upscaled["cost"]["reused_frames"] == 2
