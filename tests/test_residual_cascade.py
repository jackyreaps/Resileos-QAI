"""Residual draft, verify, and selective upscale. No provider required to close a still."""
from __future__ import annotations

import json

import numpy as np
import pytest

from resileos.harness.packet import ControlPacket
from resileos.kin.legions import LegionError
from resileos.kin.moirai import reset_coordination
from resileos.kin.studio_tools import run_forge_video, run_graphify
from resileos.studio.residual_cascade import (
    VisualPathError,
    cascade_scale,
    query_residual,
    reset_residual_index,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_coordination()
    reset_residual_index()
    yield
    reset_coordination()
    reset_residual_index()


def _const() -> np.ndarray:
    return np.full((8, 8), 0.4, dtype=np.float64)


def _ramp() -> np.ndarray:
    return np.linspace(0.0, 1.0, 64, dtype=np.float64).reshape(8, 8)


def test_cascade_attaches_layer_scale_packet_and_hash():
    packet = ControlPacket(id="still")
    out = cascade_scale(_const(), control=packet, prompt="flat field")
    assert out["outcome"] == "accepted"
    assert out["url"] is None
    assert out["produces_video"] is False
    assert out["learned"] is False
    assert out["scale_mode"] == "layer"
    assert isinstance(out["layer_scale"], float)
    assert out["oscillator"]["orientation"] == "outward"
    assert out["oscillator"]["backend"] == "kuramoto"
    assert out["compression"]["phi_compressed"] is True
    assert out["compression"]["credit_cost"] < 1.0
    assert out["compression"]["logical_bits"] < out["compression"]["reference_bits"]
    digest = out["packet_hash"]
    assert digest
    assert packet.state["residual_hash"] == digest
    assert packet.state["residual_packet"]["packet_hash"] == digest
    assert packet.state["residual_packet"]["scale_mode"] == "layer"
    assert isinstance(packet.state["residual_packet"]["layers"][0]["scale"], float)
    assert out["cascade"]["residual"] == digest
    assert out["cascade"]["path"].endswith(digest)
    sources = [item.get("source") for item in packet.evidence]
    assert "residual_core" in sources
    dumped = json.dumps(out).lower()
    assert "psnr" not in dumped
    assert "local_gen" not in dumped
    assert out["oscillator"]["backend"] != "local_gen"
    assert "http" not in dumped
    assert out["candidate"]["learned"] is False
    assert out["candidate"]["status"] == "candidate"
    assert out["checkpoint"] is None


def test_residual_draft_and_verify_without_a_provider(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    monkeypatch.delenv("RESILEOS_UPSCALE_PROVIDER", raising=False)
    calls = {"n": 0}

    def provider(payload: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/should-not-run.mp4", "payload": payload}

    accepted = run_forge_video(
        "flat",
        matrix=_const().tolist(),
        stage="draft",
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert accepted["outcome"] == "accepted"
    assert accepted["url"] is None
    assert accepted["produces_video"] is False
    digest = accepted["packet_hash"]

    verified = run_forge_video(
        "flat",
        matrix=_const().tolist(),
        residual_packet={"packet_hash": digest},
        stage="verify",
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert verified["outcome"] == "accepted"
    assert verified["checks"]["apollo"] is True
    assert verified["checks"]["hash_match"] is True
    assert verified["checks"]["hephaestus"] is True
    assert verified["url"] is None

    rejected = run_forge_video(
        "flat",
        matrix=_const().tolist(),
        residual_packet={"packet_hash": "0" * 64},
        stage="verify",
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert rejected["outcome"] == "rejected"
    assert rejected["checks"]["hash_match"] is False
    assert rejected["checks"]["apollo"] is False
    assert rejected["url"] is None

    opened = run_forge_video(
        "ramp",
        matrix=_ramp().tolist(),
        stage="verify",
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert opened["outcome"] == "inconclusive"
    assert opened["escalate"] is True
    assert opened["url"] is None
    assert opened["closes_question"] is False


def test_video_request_without_a_provider_is_unavailable(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    monkeypatch.delenv("RESILEOS_UPSCALE_PROVIDER", raising=False)
    out = run_forge_video("a hill")
    assert out["status"] == "UNAVAILABLE"
    assert out["url"] is None
    assert out["draft"] is False
    dumped = json.dumps(out).lower()
    assert "http" not in dumped
    assert "example.com" not in dumped


def test_upscale_sends_only_the_residual_delta_and_stays_off_when_closed(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    seen: list[dict] = []

    def provider(payload: str) -> dict:
        seen.append(json.loads(payload))
        return {"url": "https://cdn.test/delta.mp4", "matrix": np.full((8, 8), 0.4).tolist()}

    closed = run_forge_video("flat", matrix=_const().tolist(), stage="upscale", provider_fn=provider)
    assert seen == []
    assert closed["status"] == "not_required"
    assert closed["url"] is None
    assert closed["provider_frames"] == 0

    opened = run_forge_video("ramp", matrix=_ramp().tolist(), stage="upscale", provider_fn=provider)
    assert len(seen) == 1
    body = seen[0]
    assert body["kind"] == "residual_delta"
    assert body["full_clip"] is False
    assert body["n_frames"] == 1
    assert "prompt" not in body
    assert opened["status"] == "submitted"
    assert opened["url"] == "https://cdn.test/delta.mp4"
    assert opened["reencoded"] is True
    assert opened["provider_frames"] == 1
    assert opened["provider_cost"] < opened["full_duration_cost"]
    assert opened["packet_hash"]
    assert opened["checkpoint"] is None
    assert opened["hades_checkpoint"] is False
    assert opened["learned"] is False

    monkeypatch.delenv("RESILEOS_UPSCALE_PROVIDER", raising=False)
    missing = run_forge_video("ramp", matrix=_ramp().tolist(), stage="upscale")
    assert missing["status"] == "UNAVAILABLE"
    assert missing["url"] is None
    assert "http" not in json.dumps(missing).lower()


def test_deny_risk_does_not_call_a_provider():
    calls = {"n": 0}

    def provider(payload: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/nope.mp4", "payload": payload}

    out = run_forge_video(
        "delete the clip",
        matrix=_ramp().tolist(),
        stage="upscale",
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert out["status"] == "refused"
    assert out["url"] is None
    assert out["learned"] is False


def test_visual_path_cannot_write_facts_or_bypass_zeus():
    learned: list = []

    def learn(*args: object) -> None:
        learned.append(args)

    with pytest.raises(VisualPathError):
        cascade_scale(_const(), learn=learn)
    assert learned == []

    with pytest.raises(VisualPathError):
        cascade_scale(_const(), bypass_zeus=True)
    assert learned == []

    with pytest.raises(LegionError):
        run_forge_video("flat", matrix=_const().tolist(), learn_fn=learn)
    assert learned == []

    with pytest.raises(LegionError):
        run_forge_video("flat", matrix=_const().tolist(), bypass_zeus=True)
    assert learned == []


def test_graphify_residual_is_queried_later_and_learns_only_on_accept():
    learned: list = []

    def learn(subject: str, relation: str, obj: str) -> None:
        learned.append((subject, relation, obj))

    preview = run_graphify("Hera domain marriage", commit=False, learn_fn=learn)
    assert learned == []
    assert preview["learned"] == 0
    assert preview["residual_candidates"]
    assert preview["residual_candidates"][0]["scale_mode"] == "layer"
    assert preview["residual_candidates"][0]["packet_hash"]
    assert query_residual("Hera", "domain")["status"] == "ABSTAINED"

    committed = run_graphify("Hera domain marriage", commit=True, learn_fn=learn)
    assert learned == [("Hera", "domain", "marriage")]
    assert committed["learned"] == 1
    first = query_residual("Hera", "domain")
    second = query_residual("Hera", "domain")
    assert first["status"] == "ok"
    assert first["obj"] == "marriage"
    assert first == second
    assert first["learned"] is False

    learned.clear()
    run_graphify("sys:agency policy open", commit=True, learn_fn=learn)
    assert learned == []
    assert query_residual("sys:agency", "policy")["status"] == "ABSTAINED"

    learned.clear()
    run_graphify("what is the meaning of life?", commit=True, learn_fn=learn)
    assert learned == []
