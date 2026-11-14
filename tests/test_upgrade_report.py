"""Upgrade proposals: allowlist, auto-revert, write-only report, admin decide."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.persona.operational_tune import OperationalStore, in_bounds
from resileos.persona.upgrade_report import (
    UpgradeReport,
    classify,
    proposal_from_candidate,
)
from resileos.kin.demigods import morpheus


def test_classify_defaults_to_review_and_respects_bounds():
    assert classify("tighter_method", "tool_weights", 0.4) == "auto"
    assert classify("tighter_method", "unknown_knob", 0.4) == "review"
    assert classify("new_module", "tool_weights", 0.4) == "review"
    assert classify("schema_change", "tuning_params", 1.0) == "review"
    assert classify("tighter_method", "tool_weights", 2.0) == "review"
    assert classify("tighter_method", "tuning_params", 9.0) == "review"
    assert in_bounds("search_cache", {"q": "ok"}) is True
    huge = {"q": "x" * 5000}
    assert in_bounds("search_cache", huge) is False


def test_auto_apply_is_versioned_and_reverts_when_metric_worsens():
    report = UpgradeReport()
    store = OperationalStore()
    first = store.apply(
        target="tool_weights",
        key="search",
        value=0.7,
        metric_name="hit_rate",
        metric_before=0.5,
        report=report,
    )
    assert first["applied"] is True
    assert store.state["tool_weights"]["search"] == 0.7
    kept = store.evaluate(first["version"], 0.6, report=report)
    assert kept["reverted"] is False
    second = store.apply(
        target="metric_thresholds",
        key="accept",
        value=0.2,
        metric_name="hit_rate",
        metric_before=0.6,
        report=report,
    )
    reverted = store.evaluate(second["version"], 0.4, report=report)
    assert reverted["reverted"] is True
    assert "accept" not in store.state["metric_thresholds"]
    assert any(item.get("reverted") for item in report.auto_log)


def test_out_of_bounds_and_unverified_stay_on_review():
    store = OperationalStore()
    refused = store.apply(
        target="tool_weights",
        key="search",
        value=1.5,
        metric_name="hit_rate",
        metric_before=0.5,
    )
    assert refused["applied"] is False
    report = UpgradeReport()
    pending = report.emit(
        {"verified": False, "improvement": 0.2, "fingerprint": "abc"},
        kind="tighter_method",
        target="tool_weights",
        value=0.4,
        store=store,
    )
    assert pending["tier"] == "review"
    assert pending["proposal_status"] == "pending"
    assert pending["id"]
    auto = report.emit(
        {"verified": True, "improvement": 0.2, "fingerprint": "abc"},
        kind="tighter_method",
        target="tool_weights",
        value=0.4,
        store=store,
        metric_name="hit_rate",
        metric_before=0.1,
    )
    assert auto["proposal_status"] == "auto_applied"
    text = report.to_markdown()
    assert "Upgrade proposals" in text
    parsed = report.to_dict()
    assert parsed["writes_code"] is False
    assert "out of scope" in parsed["approved_to_pr"]
    assert "future" in parsed["email_digest"]


def test_review_approval_marks_status_and_does_not_apply_code(tmp_path, monkeypatch):
    report = UpgradeReport()
    store = OperationalStore()
    proposal = report.emit(
        {"verified": True, "improvement": 0.3, "fingerprint": "mod"},
        kind="new_module",
        target="src/resileos/persona/promote.py",
        value={"note": "add a hook"},
        store=store,
    )
    assert proposal["tier"] == "review"
    assert proposal["proposal_status"] == "pending"
    sentinel = tmp_path / "would_have_patched.py"
    original_apply = store.apply

    def boom(*args, **kwargs):
        sentinel.write_text("applied")
        return original_apply(*args, **kwargs)

    monkeypatch.setattr(store, "apply", boom)
    decided = report.approve(proposal["id"], actor="operator")
    assert decided["ok"] is True
    assert decided["applied"] is False
    assert proposal["proposal_status"] == "approved"
    assert proposal["applied_on_approve"] is False
    assert not sentinel.exists()
    assert store.version == 0
    rejected = report.reject(
        report.emit(
            {"verified": True, "improvement": 0.1, "fingerprint": "schema"},
            kind="schema_change",
            target="cascade_address",
        )["id"]
    )
    assert rejected["proposal"]["proposal_status"] == "rejected"
    assert rejected["applied"] is False


def test_morpheus_dream_stays_unverified_and_does_not_learn(monkeypatch):
    calls = {"learn": 0, "eat": 0}

    def fake_learn(*args, **kwargs):
        calls["learn"] += 1
        raise AssertionError("dream must not call learn")

    monkeypatch.setattr(morpheus, "learn_fn", fake_learn, raising=False)
    aggregates = [
        {
            "fingerprint": "agg-1",
            "error": 0.125,
            "scar": 0.0625,
            "improvement": 0.25,
            "factor_count": 4,
            "belt": 5,
            "bins": [{"bin": "mid", "n": 3}],
            "n": 3,
        }
    ]
    dreamed = morpheus.dream_factor_candidates(aggregates)
    assert dreamed["learned"] is False
    assert dreamed["writes_titanos"] is False
    assert dreamed["scar_matrix_updated"] is False
    assert dreamed["candidates"]
    assert all(item["verified"] is False for item in dreamed["candidates"])
    refused = morpheus.offer_factor_candidate(dreamed["candidates"][0], verified=False)
    assert refused["ok"] is False
    assert refused["learned"] is False
    offered = morpheus.offer_factor_candidate(dreamed["candidates"][0], verified=True)
    assert offered["ok"] is True
    assert offered["writes"] is False
    assert offered["learned"] is False
    assert offered["writes_titanos"] is False
    assert offered["envelope"]["claim"]["relation"]
    report = UpgradeReport()
    proposal = proposal_from_candidate(
        offered["candidate"], kind="tighter_method", target="tuning_params", value=1.0
    )
    # The candidate was marked verified by the gate, but the dream itself was not.
    assert dreamed["candidates"][0]["verified"] is False
    report.add(proposal)
    assert calls["learn"] == 0


# ── Leveled harness: L0 refused, L1 review only, L2 guarded ─────────────
from resileos.persona.upgrade_report import (  # noqa: E402
    L0,
    L1,
    L2,
    LEVELS,
    guard_l2,
    level_of,
)


def test_level_registry_tags_existing_modules():
    for name in ("resileos.core", "resileos.packet", "resileos.kin.hades", "resileos.abstention"):
        assert level_of(name) == L0
    assert level_of("resileos.harness.separated:zeus_head") == L0
    assert level_of("resileos.harness.tools:residual_consistency") == L0
    assert level_of("resileos.chat.router:NO_ROWS") == L0
    assert level_of("src/resileos/kin/mouth_policy.py") == L0  # require_verified
    assert level_of("resileos.harness.separated:SeparatedCycle") == L1
    assert level_of("resileos.harness.tools:risk_classify") == L1
    assert level_of("resileos.kin.demigods.morpheus") == L1
    assert level_of("resileos.harness.cascade") == L1
    assert level_of("resileos.harness.packet") == L1  # ControlPacket policy
    assert level_of("resileos.harness.tools:confidence_route") == L2
    assert level_of("src/resileos/kin/demigods/guides/atlas.md") == L2
    assert level_of("resileos.run_trace") == L2
    assert level_of("param.metric_thresholds") == L2
    assert level_of("resileos.something_new") == L1  # unlisted: review
    # A whole module that holds an L0 symbol counts as L0.
    assert level_of("resileos.harness.separated") == L0
    # Every registered module actually exists.
    import importlib.util

    for key in LEVELS:
        if key.startswith(("param.", "landing.", "scripts.")):
            continue
        mod = key.split(":")[0]
        assert importlib.util.find_spec(mod) is not None or (ROOT / "src" / mod.replace(".", "/")).exists(), key


def test_a_proposal_touching_l0_is_refused():
    report = UpgradeReport()
    store = OperationalStore()
    cand = {"verified": True, "fingerprint": "fp", "improvement": 0.4}
    out = report.emit(cand, kind="tighter_method", target="tool_weights", value=0.5, store=store,
                      paths=["src/resileos/packet.py"])
    assert out["tier"] == "refused" and out["proposal_status"] == "refused" and out["level"] == L0
    assert store.version == 0 and store.state["tool_weights"] == {}
    assert report.approve(out["id"])["ok"] is False
    assert report.proposals[-1]["proposal_status"] == "refused"
    for path in ("resileos.harness.separated:zeus_head", "resileos.kin.hades", "resileos.core"):
        assert classify("schema_change", "x", None, [path]) == "refused"


def test_an_l1_proposal_can_never_auto_apply():
    report = UpgradeReport()
    store = OperationalStore()
    cand = {"verified": True, "fingerprint": "fp", "improvement": 0.4}
    # Allowlisted target, in bounds, verified, tuning kind: still review once L1 is touched.
    for path in ("resileos.harness.cascade", "resileos.kin.demigods.morpheus",
                 "resileos.harness.tools:risk_classify", "resileos.unknown_module"):
        out = report.emit(cand, kind="tighter_method", target="tool_weights", value=0.5, store=store,
                          paths=[path])
        assert out["tier"] == "review" and out["proposal_status"] == "pending" and out["level"] == L1
    assert store.version == 0 and report.auto_log == []
    approved = report.approve(report.proposals[0]["id"])
    assert approved["ok"] is True and approved["applied"] is False and store.version == 0


def test_l2_auto_reverts_when_a_held_out_l0_or_l1_metric_drops():
    sys.path.insert(0, str(ROOT / "scripts"))
    import harness_equal_budget as suite

    report = UpgradeReport()
    store = OperationalStore()
    before = suite.held_out(store.state)
    cand = {"verified": True, "fingerprint": "route_mid", "improvement": 0.4}
    # Lowering the routing threshold answers more (the gated metric rises) ...
    out = report.emit(cand, kind="tighter_method", target="metric_thresholds", value=0.6, store=store,
                      metric_name="coverage", metric_before=13 / 24, guard_before=before,
                      paths=["resileos.harness.tools:confidence_route"])
    assert out["proposal_status"] == "auto_applied" and out["level"] == L2
    after = suite.held_out(store.state)
    assert after["params"]["route_mid"] == 0.6
    # ... but verification rate and correct abstention drop on the held-out suite.
    check = guard_l2(before, after)
    assert set(check["degraded"]) == {"verification_rate", "correct_abstention"}
    result = store.evaluate(out["version"], 17 / 24, guard_after=after, report=report)
    assert result["reverted"] is True and set(result["degraded"]) == set(check["degraded"])
    assert "route_mid" not in store.state["metric_thresholds"]
    # A change that degrades nothing guarded stays.
    keep = store.apply(target="tool_weights", key="search", value=0.5, metric_name="coverage",
                       metric_before=0.5, guard_before=before)
    assert store.evaluate(keep["version"], 0.5, guard_after=before)["reverted"] is False
