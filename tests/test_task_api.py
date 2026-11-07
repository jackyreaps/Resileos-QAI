"""Tests for task API helper."""
from resileos.ui.task_api import task_from_steps


def test_task_from_steps():
    store = {("alice", "parent_of"): {"subject": "alice", "relation": "parent_of", "obj": "bob"}}

    def ask(s, r):
        return store.get((s, r))

    out = task_from_steps(
        "child of alice",
        [{"subject": "alice", "relation": "parent_of"}],
        ask,
    )
    assert out["trace"][0]["status"] == "HIT"
    assert out["answer"]["epistemic"] == "GROUNDED"
