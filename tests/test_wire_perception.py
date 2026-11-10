"""Tests for wire_perception: legacy deprecation path vs separated path."""
import sys
from pathlib import Path
import warnings

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.kin.psyche import Psyche
from resileos.kin.wire_perception import wire_perception


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _perceived():
    return {
        "subject": "image",
        "address": {"belt": 1, "residual_bin": "mid_mid"},
        "mean_luma": 0.7,
    }


def test_legacy_eat_fn_warns_deprecation():
    psyche = Psyche()
    learned = []
    def eat_fn(claim):
        learned.append(claim)
        return type("D", (), {"accepted": True})()
    with pytest.warns(DeprecationWarning, match="without review"):
        out = wire_perception(psyche, _perceived(), eat_fn=eat_fn)
    assert "state" in out
    assert "rows" in out
    assert "judgment" in out
    assert len(learned) == 1


def test_learn_fn_path_returns_harness_fields():
    psyche = Psyche()
    learned = []
    def learn_fn(s, r, o):
        learned.append((s, r, o))
    out = wire_perception(psyche, _perceived(), learn_fn=learn_fn)
    assert "state" in out
    assert "rows" in out
    assert "judgment" in out
    assert "applied" in out
    assert "verification" in out
    assert "verdicts" in out


def test_learn_fn_path_captures_claims_not_direct_writes():
    psyche = Psyche()
    calls = []
    def learn_fn(s, r, o):
        calls.append((s, r, o))
    out = wire_perception(psyche, _perceived(), learn_fn=learn_fn)
    if out["applied"]:
        assert len(calls) >= 1
    else:
        assert calls == []


def test_learn_fn_path_includes_athena_in_verdicts():
    psyche = Psyche()
    out = wire_perception(psyche, _perceived(), learn_fn=lambda s, r, o: None)
    reviewers = [v["reviewer"] for v in out.get("verdicts", [])]
    assert "verifiers" in reviewers
    assert "athena" in reviewers


def test_learn_fn_path_unverified_by_default():
    psyche = Psyche()
    out = wire_perception(psyche, _perceived(), learn_fn=lambda s, r, o: None)
    v = out.get("verification", {})
    assert v.get("verified") is False
    reason = v.get("reason", "").lower()
    assert "evidence" in reason or "apollo" in reason or "abstain" in reason


def test_legacy_eat_fn_still_works():
    psyche = Psyche()
    eaten = []
    def eat_fn(claim):
        eaten.append(claim)
        return type("D", (), {"accepted": True})()
    out = wire_perception(psyche, _perceived(), eat_fn=eat_fn)
    assert "state" in out
    assert "rows" in out
    assert "judgment" in out
    assert "applied" not in out
    assert "verification" not in out
