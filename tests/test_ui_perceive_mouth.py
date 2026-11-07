"""Tests for perceive and mouth helpers."""
from resileos.ui.perceive import perceive
from resileos.ui.mouth import render_rows, answer_with_mouth


class _D:
    def __init__(self, accepted: bool):
        self.accepted = accepted

    def to_dict(self):
        return {"accepted": self.accepted}


def test_perceive_without_eat():
    out = perceive("a red car on a road", subject="photo1")
    assert out["candidates"]
    assert all(c["accepted"] is False for c in out["candidates"])


def test_perceive_with_eat():
    def eat(claim):
        return _D("red" in claim)

    out = perceive("red car", eat_fn=eat)
    assert any(c["accepted"] for c in out["candidates"])


def test_mouth_structured():
    rows = [{"subject": "alice", "relation": "parent_of", "obj": "bob"}]
    text = render_rows(rows, "who")
    assert "alice" in text and "bob" in text
    ans = answer_with_mouth(rows, "who")
    assert ans["backend"] == "structured"
