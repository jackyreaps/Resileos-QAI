"""Opt-in, one-step outward promotion on the cascade scales."""
import pytest

from resileos.answer.cascade_learn import (
    PREFIX,
    SCALES,
    promote,
    scale_of_subject,
    subject_at,
)
from resileos.ui.five_pin import PIN_TO_TIER, pin_for_tier


FACT = {"subject": "user:ada", "relation": "likes", "obj": "tea"}


def test_scales_and_corrected_prefixes():
    assert SCALES == ("individual", "local", "global")
    # Draft had local=world, global=org. org: is the guild hub; world: is latent.
    assert PREFIX == {"individual": "user", "local": "org", "global": "world"}
    assert subject_at("individual", "ada") == "user:ada"
    assert subject_at("local", "ada") == "org:ada"
    assert subject_at("global", "ada") == "world:ada"
    assert scale_of_subject("org:ada") == "local"
    assert pin_for_tier("hub") == "local"
    assert PIN_TO_TIER["global"] == "latent"
    with pytest.raises(ValueError, match="unknown scale"):
        subject_at("hub", "ada")


def test_unverified_is_refused_and_stays_put():
    out = promote(FACT, verified=False, to_scale="local", ident="ada", opt_in=True)
    assert out["ok"] is False
    assert out["decision"] == "refuse"
    assert out["reason"] == "unverified; stays at current scale"
    assert out["fact"]["subject"] == "user:ada"
    assert out["writes"] is False and out["learned"] is False


def test_verified_without_opt_in_is_refused():
    out = promote(FACT, verified=True, to_scale="local", ident="ada", opt_in=False)
    assert out["ok"] is False
    assert out["decision"] == "refuse"
    assert out["reason"] == "opt-in required; stays at current scale"
    out_empty = promote(FACT, verified=True, to_scale="local", ident="ada", opt_in="")
    assert out_empty["ok"] is False


def test_verified_with_opt_in_moves_one_step():
    out = promote(FACT, verified=True, to_scale="local", ident="ada", opt_in=True)
    assert out["ok"] is True
    assert out["decision"] == "accept"
    assert out["scale"] == "local"
    assert out["tier"] == "hub"
    assert out["from_scale"] == "individual"
    assert out["subject"] == "org:ada"
    assert out["relation"] == "likes"
    assert out["obj"] == "tea"
    assert out["writes"] is False and out["learned"] is False
    token = promote(FACT, verified=True, to_scale="local", ident="ada", opt_in="owner-consent")
    assert token["ok"] is True and token["subject"] == "org:ada"
    nxt = promote(
        {"subject": "org:ada", "relation": "likes", "obj": "tea"},
        verified=True,
        to_scale="global",
        ident="ada",
        opt_in=True,
    )
    assert nxt["subject"] == "world:ada"
    assert nxt["scale"] == "global"
    assert nxt["tier"] == "latent"


def test_cannot_skip_a_scale():
    out = promote(FACT, verified=True, to_scale="global", ident="ada", opt_in=True)
    assert out["ok"] is False
    assert out["decision"] == "refuse"
    assert "cannot skip a scale" in out["reason"]


def test_global_cannot_promote_further():
    fact = {"subject": "world:ada", "relation": "likes", "obj": "tea"}
    out = promote(fact, verified=True, to_scale="global", ident="ada", opt_in=True)
    assert out["ok"] is False
    assert out["reason"] == "already at global; cannot promote further"
    with pytest.raises(ValueError, match="unknown scale"):
        promote(fact, verified=True, to_scale="beyond", ident="ada", opt_in=True)
