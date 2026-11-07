"""Tests for video path and training seed."""
from resileos.ui.train_seed import seed_facts
from resileos.ui.video_gen import request_video, video_status


class _D:
    def __init__(self, accepted: bool):
        self.accepted = accepted


def test_video_not_configured(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    assert video_status()["configured"] is False
    out = request_video("a walk")
    assert out["status"] == "not_configured"


def test_seed_accepts_and_rejects():
    learned = []

    def eat(claim):
        return _D("bad" not in claim)

    def learn(s, r, o):
        learned.append((s, r, o))

    facts = [
        {"subject": "alice", "relation": "parent_of", "obj": "bob"},
        {"subject": "alice", "relation": "bad", "obj": "x"},
    ]
    out = seed_facts(facts, eat_fn=eat, learn_fn=learn)
    assert out["accepted"] == 1
    assert out["rejected"] == 1
    assert learned == [("alice", "parent_of", "bob")]
