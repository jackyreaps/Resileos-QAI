"""Kin operators + eat filter tests."""
from __future__ import annotations

from resileos.kin.eat import eat_and_learn, eat_filter
from resileos.kin.hermes import make_hermes_navigator
from resileos.kin.iris import make_iris_observer
from resileos.kin.metis import make_metis_organizer


def test_eat_accept_triple():
    d = eat_filter("Zeus domain sky")
    assert d.action == "accept"
    assert d.subject == "Zeus" and d.relation == "domain" and d.obj == "sky"


def test_eat_abstain_prose():
    d = eat_filter("what is the meaning of life?")
    assert d.action == "abstain"


def test_eat_reject_sys():
    d = eat_filter("sys:agency policy open")
    assert d.action == "reject"
    assert d.reason == "sys_subject_forbidden"


def test_eat_and_learn():
    learned = []

    def learn(s, r, o):
        learned.append((s, r, o))

    d = eat_and_learn(
        {"subject": "Athena", "relation": "domain", "obj": "wisdom"},
        learn,
        user_id="",
        seed_record=False,
    )
    assert d.action == "accept"
    assert learned == [("Athena", "domain", "wisdom")]


def test_iris_metis_pipeline():
    observe, iris_h = make_iris_observer()
    organize, metis_h = make_metis_organizer()
    assert iris_h(None, "Zeus", "domain", False) is None
    report = observe(
        metrics={"hits": 1, "misses": 9, "teaches": 0, "sessions": 5, "hit_rate": 0.1}
    )
    assert "low_hit_rate" in report.flags or "miss_dominant" in report.flags
    policy = organize(report)
    assert policy.prefer_structured is True
    assert policy.allow_mouth is False


def test_hermes_budget():
    navigate, h = make_hermes_navigator(max_items=2)
    assert h(None, "a", "b", False) is None
    ctx = [
        {"subject": "A", "relation": "r", "obj": "1"},
        "noise",
        {"subject": "B", "relation": "r", "value": "2"},
        {"foo": 1},
    ]
    out = navigate(ctx)
    assert len(out) == 2
    assert all(isinstance(x, dict) for x in out)




def test_kin_bundle_cycle_and_agency():
    from types import SimpleNamespace
    from resileos.kin.bundle import build_kin_bundle, register_declining_kin

    def zeus_like(parent, s, r, inv):
        return f"{s}:{r}"

    def iris_h(parent, s, r, inv):
        return None

    class FakeChild:
        def __init__(self, name, handler, weight=1.0):
            self.name = name
            self.handler = handler
            self.weight = weight
            self.requested_weight = weight
            self.active = True

    class FakeGroup:
        def __init__(self):
            self.children = {}
            self.eaten = []

        def add_child(self, name, handler, weight=1.0):
            ch = FakeChild(name, handler, weight)
            self.children[name] = ch
            return ch

        def _normalize_weights(self):
            pass

    g = FakeGroup()
    g.add_child("zeus", zeus_like, weight=1.0)
    b = build_kin_bundle()
    register_declining_kin(g, b, weight=0.01)
    assert "iris" in g.children
    assert g.children["iris"].handler(None, "Zeus", "domain", False) is None
    report, policy = b.cycle(
        metrics={"hits": 10, "misses": 1, "teaches": 5, "hit_rate": 0.9, "sessions": 2},
        agency_group=g,
    )
    assert report.hits == 10
    assert policy.prefer_structured is True
    g.children["zeus"].active = False
    g.eaten.append("zeus")
    report2, _ = b.cycle(
        metrics={"hits": 0, "misses": 0, "hit_rate": 0.0},
        agency_group=g,
    )
    assert "zeus" in report2.eaten_children
