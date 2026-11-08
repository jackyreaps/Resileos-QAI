"""Tests for Apollo kin."""
from resileos.kin.apollo import HEALING, apollo_cycle


class _D:
    def __init__(self, ok: bool):
        self.accepted = ok


def test_failure_lifts_with_healing():
    facts = [
        {"subject": "world:demo", "relation": "status", "obj": "bad"},
        {"subject": "world:demo", "relation": "status", "obj": "ok"},
    ]

    def eat(claim):
        return _D("bad" not in claim)

    out = apollo_cycle(facts, eat_fn=eat)
    assert out["kept"] == 1
    assert out["lifts"]
    assert out["healing"] == HEALING
    assert out["prediction"]["weight"] > 0


def test_art_keeps_without_gate():
    facts = [{"subject": "world:demo", "relation": "verse", "obj": "line"}]
    out = apollo_cycle(facts, eat_fn=lambda c: _D(False), art=True)
    assert out["art"] is True
    assert out["kept"] == 1
