"""Council + frame category tests."""
from __future__ import annotations

from resileos.kin.council import council_query
from resileos.kin.frames import (
    CAT_CONFLICT,
    CAT_ORG,
    CAT_USER,
    FRAME_ABSTAINED,
    FRAME_EXACT,
    classify_decision,
    hub_category,
)
from resileos.kin.verifiers import run_verifiers


def test_hub_categories():
    assert hub_category("user:alice") == CAT_USER
    assert hub_category("org:guild:x") == CAT_ORG


def test_classify():
    c = classify_decision("accept", subject="world:a", has_source=True)
    assert c["frame"] == FRAME_EXACT
    c2 = classify_decision("abstain")
    assert c2["frame"] == FRAME_ABSTAINED


def test_verifier_dim_on_reject():
    r = run_verifiers("sys:agency policy open")
    assert r.action == "reject"
    assert r.dim  # dim.sys


def test_council_personal_precedence():
    store = {
        ("user:Zeus", "domain"): "personal_sky",
        ("world:Zeus", "domain"): "world_sky",
        ("org:Zeus", "domain"): "org_sky",
    }

    def ask(s, r):
        return store.get((s, r))

    res = council_query("Zeus", "domain", ask, profile="personal")
    assert res.status == "CONFLICT" or res.winner_hub == "user"
    # three different values → conflict
    assert res.dim == CAT_CONFLICT
    assert res.conflicts


def test_council_agree():
    store = {
        ("user:Athena", "domain"): "wisdom",
        ("world:Athena", "domain"): "wisdom",
    }

    def ask(s, r):
        return store.get((s, r))

    res = council_query("Athena", "domain", ask, profile="personal")
    assert res.status == "ACCEPTED"
    assert res.value == "wisdom"
    assert res.frame == FRAME_EXACT
    assert res.winner_hub == "user"


def test_council_empty():
    res = council_query("Nobody", "domain", lambda s, r: None)
    assert res.status == "ABSTAINED"
