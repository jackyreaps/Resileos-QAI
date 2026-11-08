"""Tests for recursive improvement and video recesses."""
from resileos.ui.recursive_improve import recursive_step
from resileos.ui.video_codex import recess_from_codex


class _D:
    def __init__(self, ok: bool):
        self.accepted = ok


def test_recursive_keeps_accepted():
    facts = [{"subject": "world:demo", "relation": "status", "obj": "ok"}]

    def eat(claim):
        return _D("ok" in claim)

    out = recursive_step(facts, eat_fn=eat)
    assert out["kept"] >= 1
    assert out["facts"][0]["gate"]["frame"] != "abstained"


def test_recess_sequence():
    out = recess_from_codex("red desert sequence", world_id="world:demo", n_frames=3)
    assert len(out["recesses"]) == 3
    assert out["recesses"][0]["frame"] == 0
    assert out["rows"][0]["subject"] == "world:demo"
