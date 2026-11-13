"""Eat envelope: temporal validation, attention stripping, CONFLICT, Zeus commit."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from titanos import Titanos, TitanosConfig

from resileos.harness.separated import Proposal, SeparatedCycle, default_reviewers
from resileos.kin.eat_envelope import (
    ATTENTION_KEYS,
    check_envelope,
    eat_commit_envelopes,
    strip_attention,
)
from resileos.kin.hades_notes import HadesNotes


def _titanos():
    return Titanos(
        TitanosConfig(
            dim=2500, m=50, n=50, r=4, n_loops=6, seed=42,
            classical_conf=0.09, abstention_gate=0.035,
            sigma_E=10.0, sigma_k=3,
            E_sat=10.0, E_sigma=10.0, tau_sat=0.9, tau_low=0.1,
        )
    )


def _env(subject, relation, obj, vf=None, vt=None, **extra):
    claim = {"subject": subject, "relation": relation, "obj": obj}
    if vf is not None:
        claim["valid_from"] = vf
    if vt is not None:
        claim["valid_to"] = vt
    return {"claim": claim, "source": "https://example.org/a", **extra}


# ── check_envelope ────────────────────────────────────────────────────
def test_well_formed_interval_is_accepted_by_real_eat_filter():
    out = check_envelope(_env("Athens", "capital_of", "Greece", "1834-01-01"))
    assert out.action == "accept"
    assert out.valid_from == "1834-01-01"
    assert out.valid_to is None
    assert out.eat["action"] == "accept"


@pytest.mark.parametrize(
    "vf,vt,reason",
    [
        ("not-a-date", None, "invalid_valid_from"),
        (None, "13/45/2020", "invalid_valid_to"),
        ("2020-01-01", "2020-01-01", "empty_or_inverted_interval"),
        ("2021-01-01", "2020-01-01", "empty_or_inverted_interval"),
    ],
)
def test_bad_bounds_abstain(vf, vt, reason):
    out = check_envelope(_env("A", "rel", "B", vf, vt))
    assert out.action == "abstain"
    assert out.reason == reason
    assert out.eat is None  # never reached Eat


def test_valid_until_alias_is_read():
    env = {"claim": {"subject": "A", "relation": "rel", "obj": "B", "valid_until": "2000-01-01"}}
    out = check_envelope(env)
    assert out.action == "accept"
    assert out.valid_to == "2000-01-01"


def test_prose_abstains_without_parsing():
    out = check_envelope({"claim": "Paris is the capital of France", "source": "x"})
    assert out.action == "abstain"
    assert out.reason == "unstructured_prose"
    assert out.subject == ""
    none_claim = check_envelope({"claim": None, "snippet": "Paris is the capital"})
    assert none_claim.action == "abstain"


def test_attention_metrics_are_stripped_at_any_depth():
    env = _env(
        "A", "rel", "B",
        likes=10, views=99, rank=1,
        meta={"shares": 4, "kept": "yes", "nested": [{"upvotes": 3, "ok": 1}]},
    )
    env["claim"]["score"] = 0.9
    clean, removed = strip_attention(env)
    assert removed == ["likes", "rank", "score", "shares", "upvotes", "views"]
    flat = repr(clean)
    for key in removed:
        assert f"'{key}'" not in flat
    assert clean["meta"]["kept"] == "yes"
    out = check_envelope(env)
    assert out.stripped == removed
    assert out.action == "accept"
    assert {"likes", "views", "buzz", "trending"} <= ATTENTION_KEYS


def test_sys_subject_rejected_by_eat():
    out = check_envelope(_env("sys:root", "rel", "B"))
    assert out.action == "reject"


# ── commit through Zeus into the real Titanos ─────────────────────────
def test_commit_writes_titanos_with_interval_after_reviewers_approve(tmp_path):
    titan = _titanos()
    notes = HadesNotes(tmp_path / "notes.jsonl")
    out = eat_commit_envelopes(
        [
            _env("Athens", "capital_of", "Ottoman Empire", "1458-01-01", "1834-01-01", likes=5),
            _env("Athens", "capital_of", "Greece", "1834-01-01"),
        ],
        titanos=titan,
        notes=notes,
    )
    assert out["summary"]["committed"] == 2
    assert out["summary"]["reviewers"] == ["verifiers"]
    assert ("Athens", "capital_of", "Ottoman Empire", "1458-01-01", "1834-01-01") in titan.facts
    assert ("Athens", "capital_of", "Greece", "1834-01-01", None) in titan.facts
    # Half-open: 1834-01-01 belongs to Greece, not the Ottoman window.
    assert titan.ask_list("Athens", "capital_of", as_of="1834-01-01") == ["Greece"]
    assert titan.ask_list("Athens", "capital_of", as_of="1833-12-31") == ["Ottoman Empire"]
    # Attention metrics never reached the store.
    assert all("5" != str(part) for fact in titan.facts for part in fact)
    lines = notes.read()
    assert len(lines) == 1 and lines[0]["verified"] is True
    assert set(lines[0]) == {"v", "ts", "lesson", "verified", "outcome", "metrics", "checkpoint_id", "packet_hash"}


def test_overlap_with_stored_fact_is_conflict_and_not_written():
    titan = _titanos()
    titan.learn("Athens", "capital_of", "Greece", valid_from="1834-01-01", valid_to=None)
    before = list(titan.facts)
    out = eat_commit_envelopes(
        [_env("Athens", "capital_of", "Sparta", "1900-01-01", "1901-01-01")],
        titanos=titan,
    )
    result = out["results"][0]
    assert result["action"] == "conflict"
    assert result["reason"] == "overlaps_stored_fact"
    assert result["conflicts_with"][0]["obj"] == "Greece"
    assert titan.facts == before
    assert out["summary"]["committed"] == 0


def test_adjacent_half_open_windows_do_not_conflict():
    titan = _titanos()
    titan.learn("Athens", "capital_of", "Ottoman Empire", valid_from="1458-01-01", valid_to="1834-01-01")
    out = eat_commit_envelopes(
        [_env("Athens", "capital_of", "Greece", "1834-01-01")],
        titanos=titan,
    )
    assert out["results"][0]["action"] == "committed"


def test_batch_conflict_is_deterministic_and_order_free():
    a = _env("X", "leader", "P", "2000-01-01", "2010-01-01")
    b = _env("X", "leader", "Q", "2005-01-01", "2015-01-01")
    c = _env("Y", "leader", "R", "2000-01-01")
    for order in ([a, b, c], [b, c, a], [c, a, b]):
        titan = _titanos()
        out = eat_commit_envelopes(order, titanos=titan)
        by_obj = {r["obj"]: r["action"] for r in out["results"]}
        assert by_obj == {"P": "conflict", "Q": "conflict", "R": "committed"}
        assert [f[:3] for f in titan.facts] == [("Y", "leader", "R")]


def test_unbounded_multi_values_are_not_conflicts():
    titan = _titanos()
    titan.learn("Zeus", "parent_of", "Ares")
    out = eat_commit_envelopes([_env("Zeus", "parent_of", "Athena")], titanos=titan)
    assert out["results"][0]["action"] == "committed"


def test_reviewer_rejection_holds_every_claim():
    titan = _titanos()
    # Eat accepts; the verifier reviewer under Zeus runs with a locked hub
    # and rejects. Nothing is written.
    out = eat_commit_envelopes(
        [
            _env("Athens", "capital_of", "Greece", "1834-01-01"),
            _env("Rome", "capital_of", "Italy", "1871-01-01"),
        ],
        titanos=titan,
        verifier_ctx={"locked_hubs": {"default"}},
    )
    assert out["summary"]["applied"] is False
    assert [r["action"] for r in out["results"]] == ["held", "held"]
    assert "verifiers" in out["head"]["reason"]
    assert titan.facts == []


def test_nothing_reaches_zeus_when_nothing_is_accepted():
    titan = _titanos()
    out = eat_commit_envelopes([{"claim": "free text"}], titanos=titan)
    assert out["head"]["verdicts"] == []
    assert titan.facts == []


def test_review_verifiers_sees_the_interval():
    sc = SeparatedCycle()
    proposal = Proposal(
        id="p", writer="eat", action_type="eat",
        result={}, claims=[("A", "rel", "B")],
        metadata={"temporal_bounds": [("2020-01-01", "2019-01-01")]},
    )
    verdict = sc.review_verifiers(proposal)
    assert verdict.approved is False
    assert "valid_from_not_before_valid_until" in verdict.reason


def test_default_reviewers_matches_run_separated_set():
    sc = SeparatedCycle()
    assert [n for n, _ in default_reviewers(sc)] == ["verifiers"]
    assert [n for n, _ in default_reviewers(sc, ask_fn=lambda s, r: None)] == ["verifiers", "council"]
    assert [n for n, _ in default_reviewers(sc, ask_fn=lambda s, r: None, use_athena=True)] == [
        "verifiers", "council", "athena",
    ]
