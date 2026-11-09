"""Separated cycle: write / review / apply."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.harness.separated import (
    Proposal,
    SeparatedCycle,
    Verdict,
    _capture_eat,
    zeus_head,
)


def _writer_ok(**kw):
    eat = kw.get("eat_fn")
    if eat:
        eat("Zeus domain sky")
        eat({"subject": "Poseidon", "relation": "domain", "obj": "sea"})
    return {"status": "ok", "kept": 2}


def _writer_art(**kw):
    return {"status": "ok", "art": True}


# ── capture eat ─────────────────────────────────────────────────────
def test_capture_eat_string():
    claims = []
    eat = _capture_eat(claims)
    eat("Zeus domain sky")
    assert claims == [("Zeus", "domain", "sky")]


def test_capture_eat_dict():
    claims = []
    eat = _capture_eat(claims)
    eat({"subject": "A", "relation": "r", "obj": "B"})
    assert claims == [("A", "r", "B")]


def test_capture_eat_does_not_learn():
    claims = []
    eat = _capture_eat(claims)
    out = eat("A r B")
    assert out["learning"] is False


# ── propose ─────────────────────────────────────────────────────────
def test_propose_captures_claims():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    assert len(p.claims) == 2
    assert p.writer == "apollo"
    assert p.packet is not None


def test_propose_no_claims_for_art():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_art, action_type="apollo")
    assert p.claims == []


# ── review ──────────────────────────────────────────────────────────
def test_review_approve():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    v = sc.review(p, "athena", lambda _: (True, "ok", [{"matched": 2}]))
    assert v.approved is True
    assert v.reviewer == "athena"


def test_review_reject():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    v = sc.review(p, "athena", lambda _: (False, "bad frame", []))
    assert v.approved is False


# ── apply ───────────────────────────────────────────────────────────
def test_apply_only_if_approved():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    learned = []
    learn = lambda s, r, o: learned.append((s, r, o))
    v = Verdict(p.id, "athena", False, "rejected")
    out = sc.apply(p, v, learn)
    assert out["applied"] is False
    assert learned == []


def test_apply_learns_claims_when_approved():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    learned = []
    learn = lambda s, r, o: learned.append((s, r, o))
    v = Verdict(p.id, "athena", True, "ok")
    out = sc.apply(p, v, learn)
    assert out["applied"] is True
    assert out["learned"] == 2
    assert len(learned) == 2


# ── head ────────────────────────────────────────────────────────────
def test_zeus_head_all_pass():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    learned = []
    out = zeus_head(
        p,
        reviewers=[
            ("athena", lambda _: (True, "ok", [{"matched": 2}])),
            ("verifier", lambda _: (True, "ok", [{"matched": 2}])),
        ],
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
        cycle=sc,
    )
    assert out["applied"] is True
    assert len(learned) == 2
    assert len(out["verdicts"]) == 2


def test_zeus_head_first_reviewer_rejects():
    sc = SeparatedCycle()
    p = sc.propose("apollo", _writer_ok, action_type="apollo")
    learned = []
    out = zeus_head(
        p,
        reviewers=[
            ("athena", lambda _: (False, "bad frame", [])),
            ("verifier", lambda _: (True, "ok", [{"matched": 2}])),
        ],
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
        cycle=sc,
    )
    assert out["applied"] is False
    assert "athena rejected" in out["reason"]
    assert learned == []
