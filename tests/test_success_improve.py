"""Tests for golden-ladder improve cycle."""
from resileos.ui.success_improve import hop_weights, improve_cycle


class _D:
    def __init__(self, ok: bool):
        self.accepted = ok


def test_weights_are_golden():
    w = hop_weights(4)
    assert len(w) == 4
    assert all(isinstance(x, float) for x in w)


def test_only_verified_kept():
    steps = [
        {"subject": "world:demo", "relation": "status", "obj": "ok"},
        {"subject": "world:demo", "relation": "status", "obj": "bad"},
    ]

    def eat(claim):
        return _D("bad" not in claim)

    out = improve_cycle(steps, eat_fn=eat)
    assert out["hops"] == 2
    assert out["kept"] == 1
    assert out["facts"][0]["obj"] == "ok"
    assert "weight" in out["facts"][0]
