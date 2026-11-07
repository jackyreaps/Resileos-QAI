"""Tests for custom mouth and task loop."""
from resileos.ui.custom_mouth import answer, epistemic_label, render_structured
from resileos.ui.task_loop import run_task


def test_mouth_abstains_on_empty():
    out = answer([], "what is the salary")
    assert out["epistemic"] == "ABSTAINED"
    assert "No stored" in out["text"]


def test_mouth_grounded():
    rows = [{"subject": "alice", "relation": "parent_of", "obj": "bob"}]
    out = answer(rows, "parent")
    assert out["epistemic"] == "GROUNDED"
    assert "alice" in out["text"]
    assert out["backend"] == "structured"


def test_task_loop_trace():
    store = {("alice", "parent_of"): {"subject": "alice", "relation": "parent_of", "obj": "bob"}}

    def ask(s, r):
        return store.get((s, r))

    result = run_task(
        "who is the child",
        ask=ask,
        steps=[("alice", "parent_of"), ("alice", "salary")],
    )
    assert result["trace"][0]["status"] == "HIT"
    assert result["trace"][1]["status"] == "MISS"
    assert result["answer"]["epistemic"] == "GROUNDED"
