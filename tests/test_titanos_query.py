"""Tests for the Titanos query language (RES-322)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.titanos.query import (
    Name,
    Pattern,
    QueryBindingError,
    QuerySyntaxError,
    TitanosQueryEngine,
    Var,
    execute,
    parse,
    tokenize,
)


class FakeCore:
    """Minimal core exposing ask() over a dict graph."""

    def __init__(self, graph: dict[tuple[str, str], list[str]]):
        self.graph = graph

    def ask(self, anchor: str, relation: str, inverse: bool = False) -> list[str]:
        if inverse:
            # find (relation, anchor) and return subjects
            return sorted(
                s for (s, r), objs in self.graph.items()
                if r == relation and anchor in objs
            )
        return sorted(self.graph.get((anchor, relation), []))


# ── tokenizer ───────────────────────────────────────────────────────────
def test_tokenize_select_where():
    toks = tokenize("SELECT ?o WHERE alice --knows--> ?o")
    kinds = [t.kind for t in toks]
    assert kinds == ["select", "var", "where", "name", "arrow", "var"]


def test_tokenize_inverse():
    toks = tokenize("SELECT ?s WHERE ?s <--knows-- alice")
    kinds = [t.kind for t in toks]
    assert kinds == ["select", "var", "where", "var", "larrow", "name"]


def test_tokenize_comma():
    toks = tokenize("SELECT ?a, ?b WHERE ?a --r--> ?b")
    kinds = [t.kind for t in toks]
    assert "comma" in kinds


def test_tokenize_rejects_garbage():
    with pytest.raises(QuerySyntaxError):
        tokenize("SELECT ?o WHERE @#$%")


# ── parser ──────────────────────────────────────────────────────────────
def test_parse_simple():
    q = parse("SELECT ?o WHERE alice --knows--> ?o")
    assert len(q.targets) == 1
    assert q.targets[0] == Var("o")
    assert len(q.clauses) == 1
    p = q.clauses[0]
    assert p.anchor == Name("alice")
    assert p.relation == "knows"
    assert p.target == Var("o")
    assert p.inverse is False


def test_parse_two_clauses():
    q = parse(
        "SELECT ?o WHERE alice --knows--> ?o AND ?o --works_at--> acme"
    )
    assert len(q.clauses) == 2
    assert q.clauses[1].anchor == Var("o")


def test_parse_inverse_normalises():
    q = parse("SELECT ?s WHERE ?s <--knows-- alice")
    p = q.clauses[0]
    # <--knows-- alice from ?s means alice --knows--> ?s
    assert p.anchor == Name("alice")
    assert p.target == Var("s")
    assert p.inverse is False


def test_parse_multi_target():
    q = parse("SELECT ?a, ?b WHERE ?a --r--> ?b")
    assert [t.name for t in q.targets] == ["a", "b"]


def test_parse_missing_select():
    with pytest.raises(QuerySyntaxError):
        parse("WHERE alice --knows--> ?o")


def test_parse_missing_where():
    with pytest.raises(QuerySyntaxError):
        parse("SELECT ?o alice --knows--> ?o")


def test_parse_trailing_tokens():
    with pytest.raises(QuerySyntaxError):
        parse("SELECT ?o WHERE alice --knows--> ?o extra")


# ── executor ────────────────────────────────────────────────────────────
def test_execute_simple_forward():
    core = FakeCore({("alice", "knows"): ["bob", "carol"]})
    q = parse("SELECT ?o WHERE alice --knows--> ?o")
    rows = execute(core, q)
    assert sorted(r[0] for r in rows) == ["bob", "carol"]


def test_execute_inverse():
    core = FakeCore({("alice", "knows"): ["bob"]})
    q = parse("SELECT ?s WHERE ?s <--knows-- bob")
    rows = execute(core, q)
    assert [r[0] for r in rows] == ["alice"]


def test_execute_join_on_variable():
    core = FakeCore(
        {
            ("alice", "knows"): ["bob", "carol"],
            ("bob", "works_at"): ["acme"],
        }
    )
    q = parse(
        "SELECT ?o WHERE alice --knows--> ?o AND ?o --works_at--> acme"
    )
    rows = execute(core, q)
    assert [r[0] for r in rows] == ["bob"]


def test_execute_no_matches():
    core = FakeCore({})
    q = parse("SELECT ?o WHERE alice --knows--> ?o")
    assert execute(core, q) == []


def test_execute_unbound_anchor_skipped():
    """v1 does not support full scans; unbound anchor yields no rows."""
    core = FakeCore({("alice", "knows"): ["bob"]})
    q = parse("SELECT ?o WHERE ?x --knows--> ?o")
    assert execute(core, q) == []


def test_execute_multi_target_projection():
    core = FakeCore({("alice", "knows"): ["bob"]})
    q = parse("SELECT ?a, ?o WHERE alice --knows--> ?o")
    # ?a never appears in any clause, so its projection is incomplete
    # and no rows are returned (incomplete binding).
    rows = execute(core, q)
    assert rows == []


# ── engine wrapper ──────────────────────────────────────────────────────
def test_engine_parse_and_execute():
    core = FakeCore({("alice", "knows"): ["bob"]})
    eng = TitanosQueryEngine(core)
    rows = eng.execute("SELECT ?o WHERE alice --knows--> ?o")
    assert rows == [("bob",)]


def test_engine_execute_parsed():
    core = FakeCore({("alice", "knows"): ["bob"]})
    eng = TitanosQueryEngine(core)
    q = eng.parse("SELECT ?o WHERE alice --knows--> ?o")
    rows = eng.execute_parsed(q)
    assert rows == [("bob",)]
