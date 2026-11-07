"""Tests for make / continue / scene rows."""
from resileos.ui.make_world import continue_from, make_still, scene_rows


def test_make_still_rows():
    out = make_still("red desert at dusk", world_id="world:demo")
    assert out["kind"] == "still"
    assert out["rows"][0]["subject"] == "world:demo"
    assert out["address"]["belt"] == 0


def test_continue_steps_frame():
    first = make_still("start", world_id="world:demo")
    nxt = continue_from(first["address"], "next", world_id="world:demo")
    assert nxt["address"]["frame"] == first["address"]["frame"] + 1


def test_scene_prefix():
    rows = scene_rows("demo", "look", {"belt": 1, "frame": 2, "residual_bin": "r00_s1"})
    assert rows[0]["subject"] == "world:demo"
