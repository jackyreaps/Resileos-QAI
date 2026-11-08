"""Tests for deep Psyche and Athena."""
from resileos.kin.athena import judge, load_frame
from resileos.kin.psyche import Psyche


def test_psyche_frame_stack():
    p = Psyche("world:deep")
    p.push_frame(load_frame("gnosis", depth=1))
    p.push_frame(load_frame("atlas", depth=2, parent="gnosis"))
    assert p.current_frame()["label"] == "atlas"
    assert p.state["depth"] == 2
    rows = p.hub_rows()
    assert any(r["relation"] == "frame" and r["obj"] == "atlas" for r in rows)


def test_art_and_image_same_path():
    from resileos.kin.perceive_into import perceive_into
    p = Psyche("world:art")
    perceive_into(p, {"address": {"belt": 1, "residual_bin": "low_high"}, "mean_luma": 0.6})
    assert p.state["drives"]["endocrine"] == 0.6
    assert p.state["belt"] == 1
    p = Psyche("user:ada")
    p.set_drives({"endocrine": 0.8, "pineal": 0.2})
    rows = p.hub_rows()
    assert any(r["relation"] == "drive_endocrine" for r in rows)
    out = judge([], frames=[load_frame("gnosis")], drives=p.state["drives"])
    assert "drives:endocrine" in out["reading"]
    percs = [{"subject": "image", "address": {"residual_bin": "high_high"}}]
    frames = [load_frame("gnosis", depth=1)]
    out = judge(percs, frames=frames)
    assert out["frame"] == "gnosis"
    assert out["depth"] == 1
    assert "gate" in out
