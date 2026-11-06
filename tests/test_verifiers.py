"""Verifier swarm tests."""
from __future__ import annotations

from resileos.kin.eat import eat_filter
from resileos.kin.verifiers import run_verifiers


def test_swarm_accept():
    r = run_verifiers("Zeus domain sky")
    assert r.action == "accept"
    assert r.frame in ("exact", "provisional")
    assert len(r.trail) >= 3


def test_swarm_abstain_prose():
    r = run_verifiers("what is the meaning of life?")
    assert r.action == "abstain"


def test_swarm_reject_sys():
    r = run_verifiers("sys:agency policy open")
    assert r.action == "reject"
    assert r.reason == "sys_subject_forbidden"


def test_swarm_provenance_required():
    r = run_verifiers(
        {"subject": "A", "relation": "works_at", "obj": "B"},
        ctx={"require_source": True},
    )
    assert r.action == "reject"
    assert r.reason == "missing_source"


def test_swarm_contradiction():
    def ask(s, r):
        if r == "not_domain":
            return "sky"
        return None

    r = run_verifiers(
        "Zeus domain sky",
        ctx={"ask_fn": ask},
    )
    assert r.action == "reject"
    assert r.reason == "contradicts_not_relation"


def test_eat_filter_uses_swarm():
    d = eat_filter("Zeus domain sky")
    assert d.action == "accept"
    assert getattr(d, "trail", None) is not None or d.reason == "ok"
