"""Tests for perception wired into kin."""
from resileos.kin.psyche import Psyche
from resileos.kin.wire_perception import wire_perception


def test_image_wires_into_psyche_and_athena():
    p = Psyche("world:photo")
    perceived = {
        "subject": "image",
        "address": {"belt": 1, "residual_bin": "high_low"},
        "mean_luma": 0.4,
    }
    out = wire_perception(p, perceived)
    assert out["state"]["belt"] == 1
    assert out["judgment"]["modalities"] == 1
    assert any(r["relation"] == "belt" for r in out["rows"])
