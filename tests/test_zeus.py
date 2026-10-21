"""Tests for the Zeus agency child (RES-324)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.agency import AgencyGroup
from resileos.titanos.zeus import (
    ZeusConfig,
    make_zeus_handler,
    run_zeus_query,
)


# ── fake parent ────────────────────────────────────────────────────────
class FakeParent:
    """Minimal Titanos substitute for handler tests."""

    def __init__(self, answers=None, chains=None):
        self.answers = answers or {}   # (s, r, inv) -> answer
        self.chains = chains or {}     # (s, hops_tuple) -> answer
        self.ask_calls = []
        self.chain_calls = []

    def ask(self, subject, relation):
        self.ask_calls.append(("ask", subject, relation))
        return self.answers.get((subject, relation, False))

    def ask_inverse(self, subject, relation):
        self.ask_calls.append(("ask_inverse", subject, relation))
        return self.answers.get((subject, relation, True))

    def chain(self, start, relations):
        self.chain_calls.append(("chain", start, tuple(relations)))
        return self.chains.get((start, tuple(relations)))


# ── config ─────────────────────────────────────────────────────────────
def test_config_defaults():
    c = ZeusConfig()
    assert c.r_decline_threshold == 0.3
    assert c.max_hops == 4


def test_config_rejects_bad_R():
    with pytest.raises(ValueError, match="r_decline_threshold"):
        ZeusConfig(r_decline_threshold=1.5)


def test_config_rejects_bad_max_hops():
    with pytest.raises(ValueError, match="max_hops"):
        ZeusConfig(max_hops=0)


# ── handler factory ────────────────────────────────────────────────────
def test_handler_signature():
    h = make_zeus_handler()
    import inspect
    params = list(inspect.signature(h).parameters)
    assert params == ["parent", "subject", "relation", "inverse"]


def test_handler_returns_parent_answer():
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    h = make_zeus_handler()
    assert h(parent, "alice", "knows", False) == "bob"


def test_handler_returns_parent_inverse_answer():
    parent = FakeParent(answers={("bob", "knows", True): "alice"})
    h = make_zeus_handler()
    assert h(parent, "bob", "knows", True) == "alice"


def test_handler_returns_none_on_miss():
    parent = FakeParent()
    h = make_zeus_handler()
    assert h(parent, "alice", "knows", False) is None


def test_handler_returns_none_on_parent_exception():
    class BrokenParent:
        def ask(self, s, r):
            raise RuntimeError("boom")
        def ask_inverse(self, s, r):
            raise RuntimeError("boom")

    h = make_zeus_handler()
    assert h(BrokenParent(), "alice", "knows", False) is None


# ── R gate ─────────────────────────────────────────────────────────────
def test_r_gate_declines_when_unlocked():
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    h = make_zeus_handler(field_R_fn=lambda: 0.1)
    assert h(parent, "alice", "knows", False) is None
    # And parent was not consulted
    assert len(parent.ask_calls) == 0


def test_r_gate_answers_when_locked():
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    h = make_zeus_handler(field_R_fn=lambda: 0.95)
    assert h(parent, "alice", "knows", False) == "bob"


def test_r_gate_no_fn_means_locked():
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    h = make_zeus_handler()
    assert h(parent, "alice", "knows", False) == "bob"


def test_r_gate_threshold_boundary():
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    h = make_zeus_handler(field_R_fn=lambda: 0.3)
    # R == threshold is not < threshold, so Zeus proceeds
    assert h(parent, "alice", "knows", False) == "bob"


def test_r_gate_fn_exception_treated_as_unlocked():
    parent = FakeParent(answers={("alice", "knows", False): "bob"})

    def bad_fn():
        raise RuntimeError("boom")

    h = make_zeus_handler(field_R_fn=bad_fn)
    assert h(parent, "alice", "knows", False) is None


# ── composite relations ────────────────────────────────────────────────
def test_composite_relation_uses_chain():
    parent = FakeParent(
        chains={("alice", ("knows", "works_at")): "acme"}
    )
    h = make_zeus_handler(
        composite_relations={"colleague_of": ["knows", "works_at"]}
    )
    assert h(parent, "alice", "colleague_of", False) == "acme"
    assert len(parent.chain_calls) == 1
    assert parent.chain_calls[0][2] == ("knows", "works_at")


def test_composite_relation_not_expanded_for_inverse():
    parent = FakeParent(
        chains={("alice", ("knows", "works_at")): "acme"}
    )
    h = make_zeus_handler(
        composite_relations={"colleague_of": ["knows", "works_at"]}
    )
    # inverse=True falls through to ask_inverse, which returns None
    result = h(parent, "alice", "colleague_of", True)
    assert result is None
    assert len(parent.chain_calls) == 0


def test_composite_relation_exceeding_max_hops():
    parent = FakeParent(
        chains={("alice", ("a", "b", "c", "d", "e")): "x"}
    )
    h = make_zeus_handler(
        composite_relations={"too_long": ["a", "b", "c", "d", "e"]},
        cfg=ZeusConfig(max_hops=4),
    )
    result = h(parent, "alice", "too_long", False)
    assert result is None
    assert len(parent.chain_calls) == 0


def test_composite_chain_exception_returns_none():
    class BadChain(FakeParent):
        def chain(self, start, relations):
            raise RuntimeError("boom")

    h = make_zeus_handler(
        composite_relations={"colleague_of": ["knows", "works_at"]}
    )
    assert h(BadChain(), "alice", "colleague_of", False) is None


# ── closure metadata ───────────────────────────────────────────────────
def test_handler_stores_closure_metadata():
    h = make_zeus_handler(
        composite_relations={"r": ["a", "b"]},
        field_R_fn=lambda: 0.9,
    )
    assert h.__zeus_composite__ == {"r": ["a", "b"]}
    assert h.__zeus_field_R_fn__ is not None


def test_handler_stores_stream_stack_carrier():
    sentinel_stream = object()
    sentinel_stack = object()
    sentinel_carrier = object()
    h = make_zeus_handler(
        stream=sentinel_stream,
        stack=sentinel_stack,
        carrier=sentinel_carrier,
    )
    assert h.__zeus_stream__ is sentinel_stream
    assert h.__zeus_stack__ is sentinel_stack
    assert h.__zeus_carrier__ is sentinel_carrier


# ── run_zeus_query helper ──────────────────────────────────────────────
def test_run_zeus_query_selects_and_records_accept():
    group = AgencyGroup()
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    group.add_child("zeus", make_zeus_handler(), weight=1.0)

    ans = run_zeus_query(group, parent, "alice", "knows")
    assert ans == "bob"
    child = group.children["zeus"]
    assert child.query_count == 1
    assert child.accept_count == 1


def test_run_zeus_query_records_decline():
    group = AgencyGroup()
    parent = FakeParent()  # no answers
    group.add_child("zeus", make_zeus_handler(), weight=1.0)

    ans = run_zeus_query(group, parent, "alice", "knows")
    assert ans is None
    child = group.children["zeus"]
    assert child.query_count == 1
    assert child.accept_count == 0


def test_run_zeus_query_records_csi():
    group = AgencyGroup()
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    group.add_child("zeus", make_zeus_handler(), weight=1.0)

    run_zeus_query(group, parent, "alice", "knows", csi_fn=lambda: 0.82)
    child = group.children["zeus"]
    assert child.local_csi == [0.82]


def test_run_zeus_query_default_csi_is_1():
    group = AgencyGroup()
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    group.add_child("zeus", make_zeus_handler(), weight=1.0)

    run_zeus_query(group, parent, "alice", "knows")
    assert group.children["zeus"].local_csi == [1.0]


def test_run_zeus_query_no_child_returns_none():
    group = AgencyGroup()
    parent = FakeParent()
    assert run_zeus_query(group, parent, "alice", "knows") is None


def test_run_zeus_query_handler_exception_records_decline():
    group = AgencyGroup()

    def bad_handler(parent, s, r, inv):
        raise RuntimeError("boom")

    group.add_child("bad", bad_handler, weight=1.0)
    ans = run_zeus_query(group, None, "alice", "knows")
    assert ans is None
    assert group.children["bad"].accept_count == 0


def test_run_zeus_query_prune_removes_child():
    group = AgencyGroup(
        min_queries_before_eat=1,
        eat_threshold_csi=1.0,
        eat_threshold_contrib=1.0,
    )
    parent = FakeParent()  # always declines
    group.add_child("zeus", make_zeus_handler(), weight=1.0)

    for _ in range(10):
        run_zeus_query(
            group, parent, "alice", "knows",
            csi_fn=lambda: 0.0, prune=True,
        )

    assert group.children["zeus"].active is False
    assert "zeus" in group.eaten


def test_run_zeus_query_no_prune_keeps_child():
    group = AgencyGroup(
        min_queries_before_eat=1,
        eat_threshold_csi=1.0,
        eat_threshold_contrib=1.0,
    )
    parent = FakeParent()  # always declines
    group.add_child("zeus", make_zeus_handler(), weight=1.0)

    for _ in range(10):
        run_zeus_query(
            group, parent, "alice", "knows",
            csi_fn=lambda: 0.0, prune=False,
        )

    assert group.children["zeus"].active is True
    assert group.children["zeus"].query_count == 10


# ── round-robin integration ────────────────────────────────────────────
def test_group_round_robin_with_zeus():
    group = AgencyGroup()
    parent = FakeParent(answers={("alice", "knows", False): "bob"})
    group.add_child("zeus", make_zeus_handler(), weight=1.0)
    group.add_child(
        "plain", lambda p, s, r, inv: "plain_answer", weight=1.0,
    )

    run_zeus_query(group, parent, "a", "b")
    run_zeus_query(group, parent, "a", "b")

    assert group.children["zeus"].query_count == 1
    assert group.children["plain"].query_count == 1
