"""Content-free residual factors: default hub training without opt-in."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.ui.cascade_address import EPSILON, WAIST
from resileos.persona.promote import promote, subject_at
from resileos.persona.residual_factors import (
    FACTOR_RELATION,
    MIN_CONTRIBUTORS,
    aggregate_factors,
    contains_content,
    factorize,
    offer_to_eat,
)


def _factor(ident: str, energy: float = 0.25, **kw):
    return factorize(
        energy=energy,
        verified=kw.pop("verified", True),
        residual_bin=kw.pop("residual_bin", "mid"),
        factor_count=kw.pop("factor_count", 4),
        error=kw.pop("error", 0.125),
        scar_energy=kw.pop("scar_energy", 0.0625),
        previous_energy=kw.pop("previous_energy", 0.5),
        ident=ident,
        **kw,
    )


def test_unverified_or_opted_out_or_subquantum_are_dropped():
    assert factorize(energy=0.25, verified=False, ident="ada") is None
    assert factorize(energy=0.25, verified=True, opt_out=True, ident="ada") is None
    assert factorize(energy=EPSILON / 2, verified=True, ident="ada") is None
    kept = factorize(energy=EPSILON, verified=True, ident="ada")
    assert kept is not None
    assert kept["energy"] == EPSILON


def test_default_path_does_not_need_opt_in_and_waits_for_a_cohort():
    people = [_factor(name) for name in ("ada", "sam", "riley")]
    assert all(item is not None for item in people)
    refused = aggregate_factors(people[:2], to_scale="local", ident="guild")
    assert refused["ok"] is False
    assert refused["reason"] == "below minimum contributor count"
    assert refused["writes"] is False
    assert MIN_CONTRIBUTORS == 3
    accepted = aggregate_factors(people, to_scale="local", ident="guild")
    assert accepted["ok"] is True
    assert accepted["subject"] == subject_at("local", "guild")
    assert accepted["relation"] == FACTOR_RELATION
    assert accepted["count"] == 3
    assert accepted["writes"] is False
    assert accepted["learned"] is False
    assert accepted["aggregate"]["n"] == 3
    assert "ident" not in accepted["obj"]
    assert "ada" not in accepted["obj"]


def test_opt_out_ids_and_records_are_excluded_before_the_minimum():
    people = [_factor(name) for name in ("ada", "sam", "riley")]
    blocked = aggregate_factors(
        people, to_scale="local", ident="guild", opt_out_ids=["ada"]
    )
    assert blocked["ok"] is False
    assert blocked["count"] == 2


def test_waist_cap_and_content_cannot_be_recovered():
    secret = "THE_USER_SAID_THIS_PRIVATE_SENTENCE"
    pixels = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)
    record = factorize(
        energy=0.5,
        verified=True,
        factor_count=80,
        ident="ada",
    )
    assert record["factor_count"] == WAIST
    assert secret not in json.dumps(record)
    accepted = aggregate_factors(
        [_factor(name, residual_bin="hi") for name in ("ada", "sam", "riley")],
        to_scale="global",
        ident="world-facts",
    )
    blob = accepted["obj"]
    assert len(blob) <= 500
    assert contains_content(accepted, [secret], pixels=[pixels]) is False
    assert contains_content({"text": secret}, [secret]) is True


def test_richer_promotion_still_requires_opt_in():
    fact = {"subject": "user:ada", "relation": "prefers", "obj": "tea"}
    refused = promote(fact, verified=True, to_scale="local", ident="ada", opt_in=False)
    assert refused["ok"] is False
    accepted = promote(fact, verified=True, to_scale="local", ident="ada", opt_in=True)
    assert accepted["ok"] is True
    assert accepted["writes"] is False


def test_offer_to_eat_never_calls_titanos_learn(monkeypatch):
    people = [_factor(name) for name in ("ada", "sam", "riley")]
    accepted = aggregate_factors(people, to_scale="local", ident="guild")
    pending = offer_to_eat(accepted)
    assert pending["eat"] == "pending"
    assert pending["writes"] is False

    seen = {"learn": 0, "eat": 0}

    def fake_eat(envelopes, titanos=None, eat_kw=None):
        seen["eat"] += 1
        assert envelopes[0]["claim"]["relation"] == FACTOR_RELATION
        return {"summary": {"applied": 1}}

    class Stub:
        def learn(self, *args, **kwargs):
            seen["learn"] += 1
            raise AssertionError("residual factors must not call Titanos.learn")

    monkeypatch.setattr(
        "resileos.kin.eat_envelope.eat_commit_envelopes", fake_eat
    )
    out = offer_to_eat(accepted, titanos=Stub())
    assert seen["eat"] == 1
    assert seen["learn"] == 0
    assert out["eat"]["summary"]["applied"] == 1
