"""Orientation-scale visual control and residual embed address."""
import numpy as np
import pytest

from resileos.substrate.oscillator import PHI as OSC_PHI
from resileos.substrate.suite_constants import PHI
from resileos.ui.cascade_address import (
    BELT,
    ORIENTATION_SCALES,
    CASCADE_FRAMES,
    WAIST,
    cascade_address,
    frame_control,
    frame_weight,
    orientation_scale,
    phi_address,
    pin_address,
    waist_span,
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
        assert ctrl["phi_weight"] == pytest.approx(PHI ** (-(frame - 3)))
        assert ctrl["phi_weight"] == pytest.approx(phi_address(frame) / phi_address(3))
        assert ctrl["frame_control"] == frame_control(frame)


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


# ── native 3/5/9/12 frame address ──────────────────────────────────────


def test_phi_address_is_phi_power_of_the_frame():
    for frame in CASCADE_FRAMES:
        assert phi_address(frame) == PHI ** (-frame)


def test_phi_address_is_not_a_halving_step():
    for frame in CASCADE_FRAMES:
        assert phi_address(frame) != pytest.approx(2.0 ** (-frame))
    # Consecutive frames differ by a φ power, never by a factor of 2.
    pairs = zip(CASCADE_FRAMES, CASCADE_FRAMES[1:])
    for a, b in pairs:
        assert phi_address(a) / phi_address(b) == pytest.approx(PHI ** (b - a))


def test_waist_spans():
    assert WAIST == 36
    assert waist_span(12) == 3
    assert waist_span(9) == 4
    assert waist_span(3) == 12
    assert waist_span(5) is None


def test_frame_control_five_is_pentagram_orientation():
    ctrl = frame_control(5)
    assert ctrl["orientation"] is True
    assert ctrl["figure"] == "pentagram"
    assert ctrl["span"] is None
    assert ctrl["address"] == round(PHI ** -5, 6)
    for frame in (3, 9, 12):
        other = frame_control(frame)
        assert other["orientation"] is False
        assert other["figure"] == "cascade"
        assert other["span"] == WAIST // frame


@pytest.mark.parametrize("frame", [0, 1, 2, 4, 6, 8, 16, 36])
def test_phi_address_raises_on_a_non_frame(frame):
    with pytest.raises(ValueError):
        phi_address(frame)


def test_frame_weight_and_pin_address_use_the_phi_address():
    assert frame_weight(3) == pytest.approx(1.0)
    assert frame_weight(12) == pytest.approx(PHI ** -9)
    assert pin_address("global")["frame_control"] == frame_control(9)
    assert pin_address("individual")["frame_control"]["figure"] == "pentagram"


def test_cascade_search_ranks_by_phi_address():
    from resileos.chat.cascade_tools import rank_sources

    rows = [{"url": f"https://ex.org/{i}", "title": "acme widget", "snippet": ""} for i in range(12)]
    out = rank_sources(rows, "acme widget")
    by_level = {env["level"]: env["score"] for env in out["envelopes"]}
    assert by_level[0] == round(frame_weight(3), 6)
    assert by_level[1] == round(frame_weight(5), 6)
    assert by_level[2] == round(frame_weight(9), 6)
    # φ^{-9} sits under the 1/64 floor, so the 12-frame ranks drop.
    assert 3 not in by_level


def test_chroma_scales_use_the_phi_address():
    from resileos.ui.chroma import expand_variations

    code = {"chroma": [1, 1, 1, 1, 1], "hue_step": 0, "orientation": "orion"}
    pal = expand_variations(code)[0]
    assert max(pal["weights"]) <= frame_weight(9) + 1e-9


def test_frame_motion_clip_carries_its_frame_control():
    import numpy as np
    from resileos.chat.cascade_tools import clip_from_code

    pic = np.random.default_rng(0).random((8, 10, 3))
    assert clip_from_code(pic, frames=12)["frame_control"] == frame_control(12)
    assert clip_from_code(pic, frames=6)["frame_control"] == frame_control(5)
