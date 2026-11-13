"""Orientation-scale visual control and residual embed address."""
import numpy as np
import pytest

from resileos.substrate.oscillator import PHI as OSC_PHI
from resileos.substrate.suite_constants import PHI
from resileos.ui.cascade_address import (
    BELT,
    ORIENTATION_SCALES,
    cascade_address,
    orientation_scale,
    phi_level_weight,
)
from resileos.ui.residual_embed import address_triple, embed_frame


def test_orientation_scale_all_four_scales():
    expected = {
        "edge": (0, 3, "edge"),
        "sun_earth_moon": (1, 5, "near_triad"),
        "orion": (2, 9, "outer_mark"),
        "north_star": (3, 12, "pole"),
    }
    assert ORIENTATION_SCALES == tuple(expected)
    for name, (level, frame, orientation) in expected.items():
        ctrl = orientation_scale(name)
        assert ctrl["scale"] == name
        assert ctrl["scale_level"] == level
        assert "belt" not in ctrl
        assert ctrl["frame"] == frame
        assert ctrl["orientation"] == orientation
        assert ctrl["proportion"] == PHI
        assert ctrl["proportion"] == OSC_PHI
        assert ctrl["phi_weight"] == pytest.approx(PHI ** (-level))
        assert ctrl["phi_weight"] == pytest.approx(phi_level_weight(level))


def test_orientation_scale_orion_is_level_2_frame_9():
    ctrl = orientation_scale("orion")
    assert ctrl["scale_level"] == 2
    assert ctrl["frame"] == 9
    assert "belt" not in ctrl


def test_former_local_scale_is_named_edge():
    ctrl = orientation_scale("edge")
    assert ctrl["scale_level"] == 0
    assert ctrl["frame"] == 3
    assert ctrl["orientation"] == "edge"
    with pytest.raises(ValueError, match="unknown orientation scale"):
        orientation_scale("local")


def test_unknown_scale_raises():
    with pytest.raises(ValueError, match="unknown orientation scale"):
        orientation_scale("hub")
    with pytest.raises(ValueError, match="unknown orientation scale"):
        orientation_scale("global")
    with pytest.raises(ValueError, match="unknown orientation scale"):
        embed_frame(np.zeros((4, 4), dtype=np.uint8), scale="missing")


def _sample_frame():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 0] = 200
    arr[2:6, 2:6] = 40
    return arr


def test_embed_without_scale_matches_prior_keys_and_values():
    arr = _sample_frame()
    out = embed_frame(arr, belt=1, frame=3)
    assert set(out) == {
        "belt",
        "frame",
        "residual_bin",
        "mean_luma",
        "edge_density",
        "debt",
        "note",
    }
    assert out["belt"] == 1
    assert out["frame"] == 3
    assert out["residual_bin"].startswith("r")
    assert "scale" not in out
    t = address_triple(out, subject="clip")
    assert t["relation"] == "residual_address"
    assert "belt1_frame3" in t["obj"]


def test_matrix_values_are_byte_identical_with_or_without_scale():
    arr = _sample_frame()
    before = arr.tobytes()
    plain = embed_frame(arr)
    scaled = embed_frame(arr, scale="orion")
    after = arr.tobytes()
    assert after == before
    assert plain["mean_luma"] == scaled["mean_luma"]
    assert plain["edge_density"] == scaled["edge_density"]
    assert plain["debt"] == scaled["debt"]
    # residual_bin uses the original belt argument (default 0), not a
    # scale level, so the bin stays the same.
    assert plain["residual_bin"] == scaled["residual_bin"]
    assert scaled["belt"] == BELT == 5
    assert scaled["scale_level"] == 2
    assert scaled["frame"] == 9
    assert scaled["scale"] == "orion"
    assert scaled["orientation"] == "outer_mark"
    assert scaled["path"] == cascade_address(BELT, 9, scaled["residual_bin"])["path"]


def test_embed_frame_sets_address_for_each_scale():
    arr = _sample_frame()
    for name in ORIENTATION_SCALES:
        ctrl = orientation_scale(name)
        out = embed_frame(arr, scale=name)
        assert out["belt"] == BELT
        assert out["scale_level"] == ctrl["scale_level"]
        assert out["frame"] == ctrl["frame"]
        assert out["orientation"] == ctrl["orientation"]
