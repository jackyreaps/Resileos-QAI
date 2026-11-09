"""Verification gate tests: zero-match rule, evidence requirement, fail-closed.

Covers the Codio-pattern additions to resileos.harness.tools:
    verification_required   — action classification
    verify_on_stop          — strict and compat paths
    evidence_attach_raw     — summary rejection

The plain-dict tests exercise the functions directly. The integration
section exercises KinBundle.cycle() end-to-end.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.harness.tools import (
    evidence_attach_raw,
    verification_required,
    verify_on_stop,
)


# ── helpers ──────────────────────────────────────────────────────────


def _packet(**overrides):
    """Minimal packet dict. Enough for verify_on_stop, not a ControlPacket."""
    base = {
        "id": "test",
        "verified": False,
        "scars": [],
        "evidence": [],
    }
    base.update(overrides)
    return base


def _evidence(matched=5, source="probe"):
    return {"source": source, "result": {"matched": matched, "passed": matched}}


# ══════════════════════════════════════════════════════════════════════
# verification_required — action classification
# ══════════════════════════════════════════════════════════════════════


def test_verification_required_for_mutation():
    for action in ("learn", "learn_batch", "save", "train_substrate",
                   "kin_cycle", "eat", "council_query", "workbench"):
        out = verification_required(action)
        assert out["requires_verification"] is True, action
        assert out["action_type"] == action


def test_verification_optional_for_read():
    for action in ("query", "chain", "sparql", "answer", "tools", "stats",
                   "ready", "substrate_stats", "lecore_route"):
        out = verification_required(action)
        assert out["requires_verification"] is False, action


def test_verification_unknown_fails_closed():
    out = verification_required("weird_never_seen_before")
    assert out["requires_verification"] is True
    assert "fail closed" in out["reason"]


def test_verification_case_insensitive():
    assert verification_required("LEARN")["requires_verification"] is True
    assert verification_required("Query")["requires_verification"] is False


def test_verification_empty_action_fails_closed():
    assert verification_required("")["requires_verification"] is True


# ══════════════════════════════════════════════════════════════════════
# verify_on_stop — default path (backwards compatible)
# ══════════════════════════════════════════════════════════════════════


def test_default_apollo_ok_passes():
    out = verify_on_stop(_packet(), {"success": True})
    assert out["verified"] is True


def test_default_apollo_fail_preserves_compat_bug():
    """Documents the preserved fail-open on default path.

    A failed apollo with no scars returns verified=True in the default
    path (this is the pre-2026-11-09 behaviour). The strict path
    (require_evidence=True) fixes it. This test asserts the current
    default so a future fix that changes it must update the test.
    """
    out = verify_on_stop(_packet(), {"success": False})
    assert out["verified"] is True
    assert "not verified" not in out["reason"].lower()


def test_default_scars_fail():
    out = verify_on_stop(_packet(scars=["scar"]), {"success": True})
    assert out["verified"] is False
    assert "scars" in out["reason"].lower()


def test_default_no_evidence_still_passes():
    out = verify_on_stop(_packet(), {"success": True},
                         require_evidence=False)
    assert out["verified"] is True


# ══════════════════════════════════════════════════════════════════════
# verify_on_stop — strict path (require_evidence=True)
# ══════════════════════════════════════════════════════════════════════


def test_strict_apollo_ok_no_evidence_fails():
    out = verify_on_stop(_packet(), {"success": True},
                         require_evidence=True)
    assert out["verified"] is False
    assert out["reason"] == "no evidence attached"
    assert out["action"] == "run_probe_and_attach"


def test_strict_apollo_ok_with_evidence_passes():
    out = verify_on_stop(
        _packet(evidence=[_evidence(matched=5)]),
        {"success": True},
        require_evidence=True,
    )
    assert out["verified"] is True
    assert "with evidence" in out["reason"]


def test_strict_zero_matched_fails():
    out = verify_on_stop(
        _packet(evidence=[_evidence(matched=0)]),
        {"success": True},
        require_evidence=True,
    )
    assert out["verified"] is False
    assert out["reason"] == "zero matched cases in evidence"
    assert out["action"] == "widen_filter_or_abstain"


def test_strict_apollo_fail_no_scars_fails():
    """The strict path fixes the fail-open bug."""
    out = verify_on_stop(
        _packet(evidence=[_evidence(matched=5)]),
        {"success": False},
        require_evidence=True,
    )
    assert out["verified"] is False
    assert "apollo" in out["reason"].lower()
    assert out["action"] == "force_apollo"


def test_strict_scars_fail_regardless_of_evidence():
    out = verify_on_stop(
        _packet(scars=["scar"], evidence=[_evidence(matched=5)]),
        {"success": True},
        require_evidence=True,
    )
    assert out["verified"] is False
    assert "scars" in out["reason"].lower()


def test_strict_packet_verified_true_overrides_apollo_fail():
    """If the packet itself is marked verified, that wins."""
    out = verify_on_stop(
        _packet(verified=True, evidence=[_evidence(matched=5)]),
        {"success": False},
        require_evidence=True,
    )
    assert out["verified"] is True


def test_strict_summary_source_is_not_evidence():
    """An evidence entry whose source is 'summary' does not count."""
    out = verify_on_stop(
        _packet(evidence=[_evidence(matched=5, source="summary")]),
        {"success": True},
        require_evidence=True,
    )
    assert out["verified"] is False
    assert out["reason"] == "no evidence attached"


def test_strict_evidence_without_matched_key_passes():
    """Evidence without a 'matched' field does not fail the zero-check."""
    out = verify_on_stop(
        _packet(evidence=[{"source": "probe", "result": {"foo": 1}}]),
        {"success": True},
        require_evidence=True,
    )
    assert out["verified"] is True


def test_strict_none_apollo_result_fails():
    out = verify_on_stop(
        _packet(evidence=[_evidence(matched=5)]),
        None,
        require_evidence=True,
    )
    assert out["verified"] is False
    assert "apollo" in out["reason"].lower()


# ══════════════════════════════════════════════════════════════════════
# evidence_attach_raw
# ══════════════════════════════════════════════════════════════════════


def test_raw_accepts_structured_result():
    packet = _packet()
    out = evidence_attach_raw({"matched": 5, "passed": 5}, "probe", packet)
    assert len(packet["evidence"]) == 1
    assert packet["evidence"][0]["source"] == "probe"
    assert packet["evidence"][0]["result"]["matched"] == 5


def test_raw_rejects_empty_dict():
    with pytest.raises(ValueError, match="empty"):
        evidence_attach_raw({}, "probe", _packet())


def test_raw_rejects_summary_only():
    with pytest.raises(ValueError, match="summary"):
        evidence_attach_raw({"summary": "it worked"}, "probe", _packet())


def test_raw_rejects_note_only():
    with pytest.raises(ValueError, match="summary|only"):
        evidence_attach_raw({"note": "looks good"}, "probe", _packet())


def test_raw_rejects_status_only():
    with pytest.raises(ValueError, match="summary|only"):
        evidence_attach_raw({"status": "ok"}, "probe", _packet())


def test_raw_accepts_status_plus_structured():
    """status + a structured field is fine — only status-alone is rejected."""
    packet = _packet()
    evidence_attach_raw({"status": "ok", "matched": 3}, "probe", packet)
    assert len(packet["evidence"]) == 1


def test_raw_rejects_non_dict():
    with pytest.raises(TypeError, match="dict"):
        evidence_attach_raw(["not", "a", "dict"], "probe", _packet())


# ══════════════════════════════════════════════════════════════════════
# Integration — KinBundle.cycle
# ══════════════════════════════════════════════════════════════════════


def test_kin_cycle_returns_three_tuple():
    from resileos.kin.bundle import build_kin_bundle

    bundle = build_kin_bundle()
    out = bundle.cycle(metrics={"hits": 10, "misses": 1})
    assert len(out) == 3, "cycle() must return (report, policy, harness)"


def test_kin_cycle_harness_summary_has_new_keys():
    from resileos.kin.bundle import build_kin_bundle

    bundle = build_kin_bundle()
    _, _, harness = bundle.cycle(metrics={"hits": 5})
    assert "verified" in harness
    assert "reason" in harness
    assert "verification_required" in harness
    assert harness["verification_required"] is True


def test_kin_cycle_unverified_without_evidence():
    """The cycle attaches no evidence by default, so strict gate fails."""
    from resileos.kin.bundle import build_kin_bundle

    bundle = build_kin_bundle()
    _, _, harness = bundle.cycle(metrics={"hits": 5})
    assert harness["verified"] is False
    assert "evidence" in harness["reason"].lower()
