"""Tests for the scale address."""
import numpy as np

from resileos.ui.scale_address import persona_phase, scale_address


def test_persona_phase_stable():
    assert persona_phase("") == 0.0
    assert persona_phase("calm") == persona_phase("calm")
    assert persona_phase("calm") != persona_phase("sharp")


def test_scale_address_gates():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 2] = 180
    out = scale_address(arr, belt=2, frame=4, persona="calm", subject="world")
    assert out["embed"]["belt"] == 2
    assert out["triple"]["subject"] == "world"
    assert out["gate"]["frame"] in {"exact", "reconstructed", "abstained"}
    assert out["field"]["backend"] == "kuramoto"
    assert len(out["field"]["theta"]) == 3
    assert all(np.isfinite(out["field"]["theta"]))
    assert out["scale"] == "belt/frame/residual"
