"""Inter-frame motion is a residual phase step, not a pixel count."""
from __future__ import annotations

import json

import numpy as np
import pytest
from studio.codec import decode

from resileos.core import ResidualCore
from resileos.harness.packet import ControlPacket
from resileos.kin.legions import LegionError
from resileos.kin.moirai import reset_coordination
from resileos.kin.studio_tools import forge_video, run_forge_video
from resileos.studio.residual_cascade import (
    VisualPathError,
    reset_residual_index,
    run_visual_stage,
)
from resileos.substrate import suite_constants
from resileos.substrate.suite_constants import HEALING, MAGNETIC_PHASE, PHI
from resileos.ui.residual_frame import (
    apply_residual,
    bilinear_upsample,
    frame_residual,
    mirror_check,
    mirror_energy,
    mirror_residual,
    motion_scale,
    motion_vector,
    predict_frame,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_coordination()
    reset_residual_index()
    yield
    reset_coordination()
    reset_residual_index()


def _ramp_pair() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    grid_y, grid_x = np.mgrid[0:8, 0:8]
    residual = 0.01 * grid_x.astype(np.float64) + 0.02 * grid_y.astype(np.float64)
    previous = np.full((8, 8), 0.2, dtype=np.float64)
    current = previous + residual
    return previous, current, residual


def _motion_of(residual: np.ndarray) -> tuple[float, float, float]:
    gradient_y, gradient_x = np.gradient(residual)
    scale = MAGNETIC_PHASE / PHI
    return scale * float(np.mean(gradient_x)), scale * float(np.mean(gradient_y)), scale


def test_residual_is_the_frame_difference():
    previous, current, residual = _ramp_pair()
    assert np.allclose(frame_residual(current, previous), residual)
    assert np.allclose(frame_residual(current, previous), current - previous)


def test_motion_is_suite_scale_times_mean_gradient():
    _previous, _current, residual = _ramp_pair()
    motion = motion_vector(residual)
    v_x, v_y, scale = _motion_of(residual)
    assert motion_scale() == MAGNETIC_PHASE / PHI
    assert motion["scale"] == pytest.approx(scale)
    assert motion["v_x"] == pytest.approx(v_x)
    assert motion["v_y"] == pytest.approx(v_y)
    assert motion["magnitude"] == pytest.approx(float(np.hypot(motion["v_x"], motion["v_y"])))
    assert motion["unit"] == "phase_step"
    assert motion["scale"] != pytest.approx(1.0)
    assert motion["v_x"] != pytest.approx(motion["gbar_x"])
    assert set(motion) == {
        "v_x",
        "v_y",
        "magnitude",
        "scale",
        "gbar_x",
        "gbar_y",
        "unit",
    }


def test_magnetic_phase_changes_the_scale_not_the_residual(monkeypatch):
    previous, current, residual = _ramp_pair()
    before = motion_vector(residual)
    original = float(suite_constants.MAGNETIC_PHASE)
    monkeypatch.setattr(suite_constants, "MAGNETIC_PHASE", original * 2.0)
    after = motion_vector(residual)
    assert np.allclose(frame_residual(current, previous), residual)
    gradient_y, gradient_x = np.gradient(residual)
    assert after["gbar_x"] == pytest.approx(float(np.mean(gradient_x)))
    assert after["gbar_y"] == pytest.approx(float(np.mean(gradient_y)))
    assert after["gbar_x"] == pytest.approx(before["gbar_x"])
    assert after["gbar_y"] == pytest.approx(before["gbar_y"])
    assert after["scale"] == pytest.approx((original * 2.0) / PHI)
    assert after["v_x"] == pytest.approx(before["v_x"] * 2.0)
    assert after["v_y"] == pytest.approx(before["v_y"] * 2.0)


def test_phi_changes_the_scale_not_the_gradient(monkeypatch):
    _previous, _current, residual = _ramp_pair()
    before = motion_vector(residual)
    monkeypatch.setattr(suite_constants, "PHI", float(PHI) * 2.0)
    after = motion_vector(residual)
    assert after["gbar_x"] == pytest.approx(before["gbar_x"])
    assert after["gbar_y"] == pytest.approx(before["gbar_y"])
    assert after["scale"] == pytest.approx(MAGNETIC_PHASE / (float(PHI) * 2.0))
    assert after["v_x"] == pytest.approx(before["v_x"] / 2.0)


def test_motion_is_not_a_pixel_index_difference():
    previous = np.zeros((8, 8), dtype=np.float64)
    current = np.zeros((8, 8), dtype=np.float64)
    previous[2, 3] = 1.0
    current[2, 4] = 1.0
    residual = frame_residual(current, previous)
    motion = motion_vector(residual)
    prev_y, prev_x = np.unravel_index(int(np.argmax(previous)), previous.shape)
    curr_y, curr_x = np.unravel_index(int(np.argmax(current)), current.shape)
    index_step = (float(curr_x - prev_x), float(curr_y - prev_y))
    assert index_step == (1.0, 0.0)
    assert (motion["v_x"], motion["v_y"]) != pytest.approx(index_step)
    assert motion["unit"] == "phase_step"
    v_x, v_y, _scale = _motion_of(residual)
    assert motion["v_x"] == pytest.approx(v_x)
    assert motion["v_y"] == pytest.approx(v_y)


def test_mirror_is_negated_flip_and_energy_is_only_a_check():
    _previous, _current, residual = _ramp_pair()
    dual = mirror_residual(residual)
    assert np.allclose(dual, -np.flip(residual))
    assert mirror_energy(residual) == pytest.approx(float(np.mean(dual ** 2)))
    check = mirror_check(residual)
    assert check == {
        "energy": pytest.approx(float(np.mean(dual ** 2))),
        "check": True,
        "second_motion_vector": False,
    }
    assert "v_x" not in check
    assert "v_y" not in check


def test_healing_and_det_j_stay_off_the_vector(monkeypatch):
    _previous, _current, residual = _ramp_pair()
    motion = motion_vector(residual)
    monkeypatch.setattr(suite_constants, "HEALING", 1000.0)
    healed = motion_vector(residual)
    assert healed["v_x"] == pytest.approx(motion["v_x"])
    assert healed["v_y"] == pytest.approx(motion["v_y"])
    assert healed["scale"] == pytest.approx(MAGNETIC_PHASE / PHI)
    assert healed["v_x"] != pytest.approx(motion["v_x"] * HEALING)
    assert healed["v_x"] != pytest.approx(motion["v_x"] * 1000.0)
    jacobian = np.eye(2)
    assert np.linalg.det(jacobian) == pytest.approx(1.0)
    assert "det_j" not in motion
    assert "healing" not in motion
    assert motion["v_x"] != pytest.approx(1.0)
    assert motion["v_y"] != pytest.approx(1.0)


def test_decode_adds_the_residual_to_the_prediction():
    prediction = np.full((4, 4), 0.2, dtype=np.float64)
    residual = np.full((4, 4), 0.05, dtype=np.float64)
    assert np.allclose(apply_residual(prediction, residual), 0.25)


def test_bilinear_draft_and_keyframe_are_cheap_predictions():
    draft = np.array([[0.0, 1.0], [0.0, 1.0]], dtype=np.float64)
    upsampled = bilinear_upsample(draft, (4, 4))
    assert upsampled.shape == (4, 4)
    assert upsampled[0, 0] == pytest.approx(0.0)
    assert upsampled[0, -1] == pytest.approx(1.0)
    assert upsampled[-1, 0] == pytest.approx(0.0)
    assert upsampled[-1, -1] == pytest.approx(1.0)
    assert np.all(np.diff(upsampled, axis=1) >= -1e-12)

    current = np.full((8, 8), 0.4, dtype=np.float64)
    previous = np.zeros((8, 8), dtype=np.float64)
    keyframe = np.full((8, 8), 0.7, dtype=np.float64)
    _gray, predicted, kind = predict_frame(
        current,
        previous=previous,
        keyframe=keyframe,
        kind="keyframe",
    )
    assert kind == "keyframe"
    assert np.allclose(predicted, 0.7)
    assert not np.allclose(predicted, previous)

    small = np.array([[0.2, 0.4], [0.6, 0.8]], dtype=np.float64)
    _gray, bilinear, bilinear_kind = predict_frame(current, draft=small, kind="bilinear")
    assert bilinear_kind == "bilinear"
    assert bilinear.shape == current.shape
    assert np.allclose(bilinear, bilinear_upsample(small, current.shape))


def test_forge_quantizes_only_the_residual_and_decodes_onto_the_prediction():
    previous, current, residual = _ramp_pair()
    packet = ControlPacket(id="motion")
    out = run_visual_stage(
        stage="draft",
        prompt="pan",
        frames=[previous, current],
        control=packet,
    )
    assert out["outcome"] in {"accepted", "inconclusive"}
    assert out["url"] is None
    assert out["produces_video"] is False
    assert out["learned"] is False
    assert out["learn_called"] is False
    assert out["travels"] == "residual_packet"
    assert out["signal"] == "residual"
    assert out["phase_step"] is True
    assert out["healing_on_vector"] is False
    assert out["volume_on_vector"] is False
    assert out["generative"] is False
    assert out["full_clip"] is False
    assert out["prediction"] == "previous"
    assert out["candidate"]["status"] == "candidate"
    assert out["candidate"]["learned"] is False
    v_x, v_y, scale = _motion_of(residual)
    assert out["motion"]["v_x"] == pytest.approx(v_x)
    assert out["motion"]["v_y"] == pytest.approx(v_y)
    assert out["motion"]["scale"] == pytest.approx(scale)
    assert out["motion"]["unit"] == "phase_step"
    assert "v_x" not in out["mirror"]
    assert out["mirror"]["check"] is True
    assert out["mirror"]["second_motion_vector"] is False
    assert out["mirror"]["energy"] == pytest.approx(float(np.mean(mirror_residual(residual) ** 2)))
    assert packet.state["residual_hash"] == out["packet_hash"]
    assert packet.state["motion"]["v_x"] == pytest.approx(v_x)
    assert packet.state["mirror_energy"] == pytest.approx(out["mirror"]["energy"])
    sources = [item.get("source") for item in packet.evidence]
    assert "residual_core" in sources
    assert "mirror_residual" in sources
    clean = {key: value for key, value in out["residual_packet"].items() if key != "packet_hash"}
    assert "matrix" not in clean
    recon = decode(clean)
    assert np.mean((recon - residual) ** 2) < np.mean((recon - current) ** 2)
    frame = np.asarray(out["frame"], dtype=np.float64)
    assert np.allclose(frame, previous + recon, atol=1e-5)
    assert out["oscillator"]["orientation"] == "outward"
    assert out["oscillator"]["backend"] == "kuramoto"
    dumped = json.dumps(out).lower()
    assert "http" not in dumped
    assert "psnr" not in dumped


def test_verify_uses_the_packet_hash_and_failures_do_not_ask_for_a_clip():
    previous, current, _residual = _ramp_pair()
    drafted = run_visual_stage(stage="draft", prompt="pan", frames=[previous, current])
    verified = run_visual_stage(
        stage="verify",
        prompt="pan",
        frames=[previous, current],
        residual_packet={"packet_hash": drafted["packet_hash"]},
    )
    assert verified["checks"]["hash_match"] is True
    assert verified["checks"]["residual_consistency"] is True
    assert verified["checks"]["hephaestus"] is True
    assert verified["url"] is None
    assert verified["produces_video"] is False
    assert verified["packet_hash"] == drafted["packet_hash"]
    assert verified["generative"] is False
    if verified["outcome"] == "accepted":
        assert verified["checks"]["apollo"] is True
        assert verified["retry"] is None
    else:
        assert verified["retry"] == "cheap_draft"
        assert verified["full_clip"] is False

    rejected = run_visual_stage(
        stage="verify",
        prompt="pan",
        frames=[previous, current],
        residual_packet={"packet_hash": "0" * 64},
    )
    assert rejected["outcome"] == "rejected"
    assert rejected["checks"]["hash_match"] is False
    assert rejected["checks"]["apollo"] is False
    assert rejected["retry"] == "residual_packet"
    assert rejected["url"] is None
    assert rejected["full_clip"] is False


def test_keyframe_and_bilinear_drafts_are_wired_without_a_provider():
    current = np.full((8, 8), 0.5, dtype=np.float64)
    current[:, 4:] = 0.8
    keyframe = np.full((8, 8), 0.5, dtype=np.float64)
    keyed = run_visual_stage(
        stage="draft",
        prompt="key",
        matrix=current,
        keyframe=keyframe,
        prediction="keyframe",
    )
    assert keyed["prediction"] == "keyframe"
    assert keyed["url"] is None
    assert keyed["produces_video"] is False
    residual = current - keyframe
    v_x, v_y, _scale = _motion_of(residual)
    assert keyed["motion"]["v_x"] == pytest.approx(v_x)
    assert keyed["motion"]["v_y"] == pytest.approx(v_y)

    draft = np.array([[0.5, 0.8], [0.5, 0.8]], dtype=np.float64)
    lifted = run_visual_stage(
        stage="draft",
        prompt="draft",
        matrix=current,
        draft=draft,
        prediction="bilinear",
    )
    assert lifted["prediction"] == "bilinear"
    assert lifted["url"] is None
    prediction = bilinear_upsample(draft, current.shape)
    v_x, v_y, _scale = _motion_of(current - prediction)
    assert lifted["motion"]["v_x"] == pytest.approx(v_x)
    assert lifted["motion"]["v_y"] == pytest.approx(v_y)
    assert lifted["provider_frames"] == 0


def test_no_fake_video_url_when_no_provider_is_configured(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    monkeypatch.delenv("RESILEOS_UPSCALE_PROVIDER", raising=False)
    previous, current, _residual = _ramp_pair()
    drafted = run_forge_video("pan", frames=[previous.tolist(), current.tolist()], stage="draft")
    assert drafted["url"] is None
    assert drafted["produces_video"] is False
    assert drafted["status"] in {"accepted", "inconclusive", "rejected"}
    assert "http" not in json.dumps(drafted).lower()

    bare = run_forge_video("a hill")
    assert bare["status"] == "UNAVAILABLE"
    assert bare["url"] is None
    assert bare["draft"] is False
    assert "http" not in json.dumps(bare).lower()

    calls = {"n": 0}

    def provider(payload: str) -> dict:
        calls["n"] += 1
        return {"url": "https://cdn.test/should-not-run.mp4", "payload": payload}

    held = run_forge_video(
        "pan",
        frames=[previous.tolist(), current.tolist()],
        stage="draft",
        provider_fn=provider,
    )
    assert calls["n"] == 0
    assert held["url"] is None
    assert "http" not in json.dumps(held).lower()


def test_upscale_sends_the_residual_or_stays_unavailable(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    monkeypatch.delenv("RESILEOS_UPSCALE_PROVIDER", raising=False)
    previous = np.zeros((8, 8), dtype=np.float64)
    current = (np.indices((8, 8)).sum(axis=0) % 2).astype(np.float64)
    missing = run_forge_video(
        "noise",
        frames=[previous.tolist(), current.tolist()],
        stage="upscale",
    )
    assert missing["status"] == "UNAVAILABLE"
    assert missing["url"] is None
    assert missing["produces_video"] is False
    assert missing["full_clip"] is False
    assert missing["retry"] == "cheap_draft"
    assert "http" not in json.dumps(missing).lower()

    seen: list[dict] = []

    def provider(payload: str) -> dict:
        seen.append(json.loads(payload))
        return {"url": "https://cdn.test/delta.mp4"}

    opened = run_forge_video(
        "noise",
        frames=[previous.tolist(), current.tolist()],
        stage="upscale",
        provider_fn=provider,
    )
    assert opened["status"] == "submitted"
    assert opened["produces_video"] is False
    assert opened["full_clip"] is False
    assert len(seen) == 1
    body = seen[0]
    assert body["kind"] == "residual_delta"
    assert body["full_clip"] is False
    assert body["n_frames"] == 1
    assert "prompt" not in body
    assert body["motion"]["unit"] == "phase_step"
    delta = np.asarray(body["frames"][0]["delta"], dtype=np.float64).reshape(8, 8)
    assert np.allclose(delta, current - previous, atol=1e-5)
    assert opened["url"] == "https://cdn.test/delta.mp4"


def test_single_matrix_stays_a_still():
    out = run_forge_video("flat", matrix=np.full((8, 8), 0.4).tolist(), stage="draft")
    assert "motion" not in out
    assert out["url"] is None
    assert out["produces_video"] is False
    assert out["learned"] is False


def test_learn_and_bypass_zeus_are_refused_and_the_scar_is_not_stepped(monkeypatch):
    previous, current, _residual = _ramp_pair()
    frames = [previous, current]
    learned: list = []
    steps = {"n": 0}
    original = ResidualCore.step

    def _spy(self, *args, **kwargs):
        steps["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ResidualCore, "step", _spy)

    def learn(*args: object) -> None:
        learned.append(args)

    with pytest.raises(VisualPathError):
        run_visual_stage(stage="draft", prompt="pan", frames=frames, learn=learn)
    with pytest.raises(VisualPathError):
        run_visual_stage(stage="draft", prompt="pan", frames=frames, bypass_zeus=True)
    with pytest.raises(VisualPathError):
        forge_video(
            {"id": "motion", "budget_remaining": {"steps": 8, "cost": 1.0}},
            prompt="pan",
            frames=frames,
            learn=learn,
        )
    with pytest.raises(LegionError):
        run_forge_video("pan", frames=[previous.tolist(), current.tolist()], learn_fn=learn)
    with pytest.raises(LegionError):
        run_forge_video("pan", frames=[previous.tolist(), current.tolist()], bypass_zeus=True)
    assert learned == []

    out = run_visual_stage(stage="draft", prompt="pan", frames=frames)
    assert out["learned"] is False
    assert out["learn_called"] is False
    assert steps["n"] == 0
