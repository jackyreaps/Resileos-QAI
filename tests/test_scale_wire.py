"""Tests for scale wiring."""
import numpy as np

from resileos.ui.scale_wire import perceive_with_scale, task_with_scale


def test_task_with_scale():
    store = {("alice", "parent_of"): {"subject": "alice", "relation": "parent_of", "obj": "bob"}}

    def ask(s, r):
        return store.get((s, r))

    out = task_with_scale(
        "child",
        [{"subject": "alice", "relation": "parent_of"}],
        ask,
        persona="calm",
    )
    assert "scale" in out
    assert out["scale"]["gate"]["frame"] in {"exact", "reconstructed", "abstained"}


def test_perceive_with_scale():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 1] = 200
    out = perceive_with_scale(arr, persona="calm", belt=1)
    assert "candidates" in out
    assert "scale" in out
    assert out["scale"]["address"]["belt"] == 1
