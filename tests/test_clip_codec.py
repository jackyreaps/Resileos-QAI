"""Temporal residual clip codec. Compression of frames that already exist."""
from __future__ import annotations

import json

import numpy as np
import pytest

from resileos.core import ResidualCore
from resileos.studio.clip_codec import (
    REUSE_MARK,
    TEMPORAL_SIGMA,
    decode_sequence,
    encode_sequence,
    numeric_packet,
    prepare_frames,
    public_sequence,
    sequence_digest,
)
from resileos.ui.residual_frame import frame_residual, mirror_check, motion_vector


def _edge() -> list[np.ndarray]:
    image = np.zeros((8, 8), dtype=np.float64)
    image[:, :4] = 0.2
    image[:, 4:] = 0.8
    return [image, image.copy(), image.copy()]


def test_encode_does_not_step_or_update_the_scar(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("clip codec called ResidualCore.step or _scar_update")

    monkeypatch.setattr(ResidualCore, "step", boom)
    monkeypatch.setattr(ResidualCore, "_scar_update", boom)

    def address(*_args, **kwargs):
        raise AssertionError(f"clip codec called scale_address step_core={kwargs.get('step_core')}")

    monkeypatch.setattr("resileos.ui.scale_address.scale_address", address)
    encoded = encode_sequence(_edge())
    assert encoded["scar_matrix_updated"] is False
    assert encoded["learned"] is False
    assert encoded["learn_called"] is False
    assert encoded["step_core"] is False
    assert encoded["generative"] is False
    assert encoded["scale_mode"] == "layer"


def test_chain_reuses_frames_under_the_sigma_gate():
    frames = _edge()
    encoded = encode_sequence(frames)
    sequence = public_sequence(encoded)
    assert sequence["version"] == "studio-clip/1"
    assert sequence["n_frames"] == 3
    assert sequence["deltas"] == []
    assert sequence["sequence_hash"] == sequence_digest(sequence["base"], sequence["deltas"])
    base = numeric_packet(sequence["base"])
    assert base["scale_mode"] == "layer"
    assert isinstance(base["layers"][0]["scale"], float)
    assert not isinstance(base["layers"][0]["scale"], list)
    decoded = decode_sequence(sequence)
    assert len(decoded) == 3
    prepared = prepare_frames(frames)
    residual = frame_residual(prepared[1], decoded[0])
    motion = motion_vector(residual)
    mirror = mirror_check(residual)
    step = encoded["steps"][1]
    assert step["kind"] == "reuse"
    assert step["disposition"] == REUSE_MARK
    assert step["temporal_magnitude"] <= TEMPORAL_SIGMA
    assert step["escalated"] is False
    assert step["motion"]["v_x"] == pytest.approx(motion["v_x"])
    assert step["motion"]["v_y"] == pytest.approx(motion["v_y"])
    assert step["motion"]["scale"] == pytest.approx(motion["scale"])
    assert step["motion"]["unit"] == "phase_step"
    assert step["mirror"]["energy"] == pytest.approx(mirror["energy"])
    assert step["mirror"]["second_motion_vector"] is False
    bits = sequence["bits_per_frame"]
    assert bits["base"] == sequence["base"]["logical_bits"] == 96
    assert bits["deltas"] == []
    assert bits["mean_delta"] == pytest.approx(0.0)
    assert bits["reused_frames"] == 2
    assert bits["generative_frames"] == 0
    assert bits["base"] > bits["mean_delta"]
    assert sequence["keyframe_ids"] == [0]
    assert encoded["energy_closed"] is True
    blob = json.loads(json.dumps(sequence))
    assert sequence_digest(blob["base"], blob["deltas"]) == sequence["sequence_hash"]


def _shifted_edge() -> list[np.ndarray]:
    frames = []
    for shift in (0, 1, 2):
        image = np.zeros((8, 8), dtype=np.float64)
        cut = 4 + shift
        image[:, :cut] = 0.2
        image[:, cut:] = 0.8
        frames.append(image)
    return frames


def test_motion_over_the_sigma_gate_stores_delta_packets():
    encoded = encode_sequence(_shifted_edge())
    sequence = public_sequence(encoded)
    assert sequence["steps"][1]["disposition"] == "escalated"
    assert sequence["steps"][1]["temporal_magnitude"] > TEMPORAL_SIGMA
    assert sequence["steps"][2]["escalated"] is True
    bits = sequence["bits_per_frame"]
    assert bits["base"] == 96
    assert bits["deltas"] == [96, 96]
    assert bits["mean_delta"] == pytest.approx(96.0)
    assert bits["reused_frames"] == 0
    assert bits["generative_frames"] == 2
    assert sequence["keyframe_ids"] == [0, 1, 2]
    decoded = decode_sequence(sequence)
    assert len(decoded) == 3


def test_motion_helpers_are_called_not_reimplemented(monkeypatch):
    seen = {"motion": 0, "mirror": 0}
    real_motion = motion_vector
    real_mirror = mirror_check

    def motion(residual):
        seen["motion"] += 1
        return real_motion(residual)

    def mirror(residual):
        seen["mirror"] += 1
        return real_mirror(residual)

    monkeypatch.setattr("resileos.studio.clip_codec.motion_vector", motion)
    monkeypatch.setattr("resileos.studio.clip_codec.mirror_check", mirror)
    encode_sequence(_edge())
    assert seen["motion"] == 3
    assert seen["mirror"] == 3


def test_a_wide_frame_is_projected_before_it_is_coded():
    wide = np.full((32, 32), 0.4, dtype=np.float64)
    encoded = encode_sequence([wide, wide])
    assert encoded["shape"] == [8, 8]
    assert encoded["bits_per_frame"]["frames"] == 2


def test_sequence_records_keep_floor_without_changing_the_gate():
    from resileos.ui.cascade_address import keep_packet

    encoded = encode_sequence(_edge())
    assert encoded["kept"] is keep_packet(encoded["energy"])
    assert encoded["sigma"] == TEMPORAL_SIGMA

