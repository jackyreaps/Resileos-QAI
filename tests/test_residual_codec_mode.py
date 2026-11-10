"""Residual codec mode: round trip, candidates, external sampler, demi-gods."""
from __future__ import annotations

import numpy as np
import pytest

from resileos.core import ResidualCore
from resileos.studio.candidates import register_candidate
from resileos.studio.codecs import LearnedConvCodec, open_codec
from resileos.studio.external_sampler import SamplerOff, resolve_external_sampler
from resileos.studio.gate import gate_studio_packet
from resileos.studio.service import propose_external, round_trip, sample_toy_prior, study_prior_report
from resileos.ui.studio_app import register_studio_candidate


def test_round_trip_stores_component_scales_and_passes_the_gate():
    codec = open_codec("pca_component")
    image = codec.holdout_matrix(0)  # type: ignore[attr-defined]
    out = round_trip(image)
    assert out["learned"] is False
    assert out["scar_matrix_updated"] is False
    assert out["packet"]["scale_mode"] == "component"
    assert out["packet"]["scales_per_layer"] == [4, 4, 4, 4]
    assert out["packet"]["logical_bits"] > 0
    assert out["packet"]["packed_bytes"] >= out["packet"]["logical_bits"] // 8
    assert out["metrics"]["psnr"] is not None
    assert out["metrics"]["psnr"] > 0
    assert 0.0 <= out["metrics"]["global_ssim"] <= 1.0
    assert out["decoded"].shape == (8, 8)
    gate = out["gate"]
    assert gate["well_formed"] is True
    assert gate["residual_consistency"]["consistent"] is True
    assert gate["hephaestus"]["verified"] is True
    assert gate["themis"]["verified"] is True
    assert gate["learned"] is False
    assert gate["scar_matrix_updated"] is False


def test_round_trip_does_not_step_the_core_or_update_scars(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("the codec mode touched the core")

    monkeypatch.setattr(ResidualCore, "step", boom)
    monkeypatch.setattr(ResidualCore, "_scar_update", boom)
    codec = open_codec("pca_component")
    image = codec.holdout_matrix(4)  # type: ignore[attr-defined]
    out = round_trip(image)
    assert out["gate"]["hephaestus"]["verified"] is True


def test_candidate_registration_never_calls_learn():
    def boom(*_args, **_kwargs):
        raise AssertionError("learn was called")

    record = register_candidate(
        kind="image",
        path="candidate://test",
        title="CANDIDATE toy",
        note="not a fact",
        learn=boom,
        learn_batch=boom,
        world_register=boom,
    )
    assert record["status"] == "candidate"
    assert record["learned"] is False
    assert record["learn_called"] is False
    assert record["ok"] is True

    via_studio = register_studio_candidate("image", "candidate://studio", "CANDIDATE studio")
    assert via_studio["learned"] is False
    assert via_studio["status"] == "candidate"


def test_toy_sample_is_a_candidate_and_is_not_learned():
    out = sample_toy_prior(1, seed=0)
    assert out["learned"] is False
    assert out["scar_matrix_updated"] is False
    assert out["status"] == "candidate"
    candidate = out["candidate"]
    assert candidate["learned"] is False
    assert candidate["status"] == "candidate"
    assert candidate["learn_called"] is False
    assert "learn" not in candidate["path"]
    assert out["gate"]["themis"]["verified"] is True
    assert out["gate"]["hephaestus"]["verified"] is True
    assert out["image"].shape == (8, 8)
    study = out["study"]
    assert study["available"] is True
    assert study["exact_train_copies"] == 0
    assert study["config"]["scale_mode"] == "component"


def test_external_sampler_is_off_by_default(monkeypatch):
    monkeypatch.delenv("RESILEOS_EXTERNAL_SAMPLER", raising=False)
    sampler = resolve_external_sampler()
    assert sampler.enabled is False
    with pytest.raises(SamplerOff):
        sampler.propose()
    refused = propose_external(env={})
    assert refused["enabled"] is False
    assert refused["candidate"] is None
    assert refused["learned"] is False


def test_unknown_external_sampler_is_not_loaded():
    sampler = resolve_external_sampler({"RESILEOS_EXTERNAL_SAMPLER": "p-h3-image"})
    assert sampler.enabled is False
    assert "not loaded" in sampler.reason
    with pytest.raises(SamplerOff):
        sampler.propose()


def test_fake_external_sampler_proposes_a_gated_candidate():
    out = propose_external(env={"RESILEOS_EXTERNAL_SAMPLER": "fake"}, condition={"seed": 2})
    assert out["enabled"] is True
    assert out["learned"] is False
    assert out["packet"]["scale_mode"] == "component"
    assert out["gate"]["hephaestus"]["verified"] is True
    assert out["gate"]["residual_consistency"]["consistent"] is True
    assert out["gate"]["themis"]["verified"] is True
    assert out["candidate"]["status"] == "candidate"
    assert out["candidate"]["learned"] is False
    assert out["image"].shape == (8, 8)


def test_malformed_packet_fails_hephaestus_and_themis():
    packet = {
        "version": "studio-codec/1",
        "shape": [8, 8],
        "rank": 2,
        "n_layers": 1,
        "scale_mode": "layer",
        "layers": [{"Ub": np.ones((8, 2)), "Vb": np.ones((2, 8)), "scale": 1.0}],
    }
    gate = gate_studio_packet(packet)
    assert gate["well_formed"] is False
    assert gate["hephaestus"]["verified"] is False
    assert gate["themis"]["verified"] is False
    assert gate["residual_consistency"]["consistent"] is False
    assert gate["learned"] is False


def test_learned_conv_codec_is_the_drop_in_and_is_unavailable():
    codec = LearnedConvCodec()
    assert codec.available is False
    with pytest.raises(Exception, match="No conv encoder is trained"):
        codec.encode_matrix(np.zeros((8, 8)))
    with pytest.raises(Exception, match="No conv encoder is trained"):
        round_trip(np.zeros((8, 8)), codec_name="learned_conv")


def test_study_report_matches_the_committed_measurement():
    report = study_prior_report()
    assert report["holdout_reconstruction_psnr"] == pytest.approx(13.884122324884922)
    assert report["same_class_nearest_train_rate"] == pytest.approx(0.4125)
    assert report["exact_train_copies"] == 0
