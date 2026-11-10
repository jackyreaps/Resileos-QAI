"""Integration tests for harness + Kin cycle."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    apollo_success,
    budget_and_stuck_guard,
    confidence_route,
    residual_consistency,
    risk_classify,
    verify_on_stop,
)


# ── tool primitives ─────────────────────────────────────────────────
def test_risk_classify_allow():
    assert risk_classify("read file")["risk_class"] == "allow"


def test_risk_classify_deny():
    assert risk_classify("rm -rf /")["risk_class"] == "deny"


def test_risk_classify_ask():
    assert risk_classify("git commit")["risk_class"] == "ask"


def test_confidence_route_high():
    out = confidence_route({"probability": 0.995})
    assert out["route"] == "residual_or_apollo"


def test_confidence_route_mid():
    out = confidence_route({"probability": 0.85})
    assert out["route"] == "cascade"


def test_confidence_route_low():
    out = confidence_route({"probability": 0.4})
    assert out["route"] == "escalate_or_abstain"


def test_verify_on_stop_passes_with_apollo():
    packet = ControlPacket(id="t").to_dict()
    v = verify_on_stop(packet, {"success": True})
    assert v["verified"] is True


def test_verify_on_stop_fails_with_scars():
    packet = ControlPacket(id="t").to_dict()
    packet["scars"] = ["unresolved"]
    v = verify_on_stop(packet, {"success": False})
    assert v["verified"] is False
    assert v["action"] == "force_apollo_or_cleanup"


# ── new functions ────────────────────────────────────────────────────
def test_residual_consistency_clean():
    packet = ControlPacket(id="t").to_dict()
    out = residual_consistency(packet)
    assert out["consistent"] is True


def test_residual_consistency_scars():
    packet = ControlPacket(id="t").to_dict()
    packet["scars"] = ["scar_a"]
    out = residual_consistency(packet)
    assert out["consistent"] is False


def test_residual_consistency_bad_evidence():
    packet = ControlPacket(id="t").to_dict()
    packet["evidence"] = [
        {"source": "residual_core", "result": {"packet_hash": None}},
    ]
    out = residual_consistency(packet)
    assert out["consistent"] is False


def test_apollo_success_ok():
    assert apollo_success({"status": "ok"})["success"] is True


def test_apollo_success_scarred():
    assert apollo_success({"status": "scarred"})["success"] is False


def test_apollo_success_missing_status():
    assert apollo_success({})["success"] is False


# ── budget guard ─────────────────────────────────────────────────────
def test_budget_guard_ok():
    packet = ControlPacket(id="t").to_dict()
    assert budget_and_stuck_guard(packet)["ok"] is True


def test_budget_guard_exhausted():
    packet = ControlPacket(id="t").to_dict()
    packet["budget_remaining"] = {"steps": 0, "cost": 1.0, "tokens": 100}
    assert budget_and_stuck_guard(packet)["ok"] is False


# ── Kin cycle integration ────────────────────────────────────────────
def test_kin_cycle_returns_three_tuple():
    from resileos.kin.bundle import build_kin_bundle

    bundle = build_kin_bundle()
    out = bundle.cycle(metrics={"hits": 10, "misses": 1})
    assert len(out) == 3, "cycle() must return (report, policy, harness)"
    report, policy, harness = out
    assert report is not None
    assert policy is not None
    assert "verified" in harness
    assert isinstance(harness["verified"], bool)


def test_kin_cycle_with_residual_packet_hash():
    from resileos.kin.bundle import build_kin_bundle

    bundle = build_kin_bundle()
    stub = type("Stub", (), {"packet_hash": "abc123"})()
    report, policy, harness = bundle.cycle(
        metrics={"hits": 5},
        residual_packet=stub,
    )
    assert "consistency" in harness
