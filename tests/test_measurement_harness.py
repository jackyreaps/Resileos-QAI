"""Measurement harnesses: pair list, skipped LLM leg, mouth-policy leaks."""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_bench_vs_llm():
    path = ROOT / "scripts" / "ops" / "bench_vs_llm.py"
    spec = importlib.util.spec_from_file_location("bench_vs_llm_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_memory_bench_keeps_the_3_known_and_12_unknown_pairs():
    module = _load_bench_vs_llm()
    assert len(module.KNOWN) == 3
    assert len(module.UNKNOWN) == 12
    assert [row[2] for row in module.KNOWN] == ["sky", "sea", "wisdom"]
    assert all(row[2] is None for row in module.UNKNOWN)


def test_llm_leg_skips_without_inventing_scores_or_printing_the_key(monkeypatch):
    monkeypatch.delenv("BENCH_LLM_URL", raising=False)
    monkeypatch.setenv("BENCH_LLM_KEY", "super-secret-demo-key-should-not-appear")
    module = _load_bench_vs_llm()
    report = module.llm_leg()
    blob = json.dumps(report)
    assert report["status"] == "skipped"
    assert report["exact_match_rate"] is None
    assert report["invent_rate"] is None
    assert report["url_set"] is False
    assert report["key_set"] is True
    assert "super-secret-demo-key-should-not-appear" not in blob
    assert "BENCH_LLM_URL unset" in report["reason"]

    monkeypatch.setenv("BENCH_LLM_URL", "http://127.0.0.1:9/complete?token=super-secret-demo-key-should-not-appear")
    monkeypatch.delenv("BENCH_LLM_KEY", raising=False)
    report = module.llm_leg()
    blob = json.dumps(report)
    assert report["status"] == "skipped"
    assert report["exact_match_rate"] is None
    assert report["invent_rate"] is None
    assert "super-secret-demo-key-should-not-appear" not in blob
    assert "127.0.0.1" not in blob


def test_redact_strips_a_key_that_a_response_echoed(monkeypatch):
    monkeypatch.setenv("BENCH_LLM_KEY", "echoed-secret-value")
    module = _load_bench_vs_llm()
    assert module.redact_text("token echoed-secret-value end") == "token [redacted] end"


def test_require_verified_default_stays_true():
    from resileos.kin.mouth_policy import should_render_prose

    default = inspect.signature(should_render_prose).parameters["require_verified"].default
    assert default is True
    source = (ROOT / "src" / "resileos" / "kin" / "mouth_policy.py").read_text(encoding="utf-8")
    assert "require_verified: bool = True" in source


def test_mouth_policy_leak_count_is_zero():
    from bench.mouth_leak import run_harness

    report = run_harness()
    assert report["require_verified_default"] is True
    assert report["policy"]["verified_control_opens"] is True
    assert report["policy"]["client_closed_stays_closed"] is True
    assert report["spoken"]["factual_prose_when_unverified"] == 0
    assert report["spoken"]["writer_token_in_text_when_unverified"] == 0
    assert report["policy"]["opened_when_unverified"] == 0
    assert report["leak_count"] == 0


def test_exact_query_catalog_uses_only_single_valued_hops():
    from bench.latency_m5 import exact_asks, exact_chains

    facts = [
        ("Uranus", "parent_of", "Cronus"),
        ("Cronus", "is_a", "titan"),
        ("Cronus", "parent_of", "Zeus"),
        ("Cronus", "parent_of", "Hera"),
        ("Zeus", "domain", "sky"),
    ]
    asks = exact_asks(facts)
    assert ("Uranus", "parent_of", "Cronus") in asks
    assert ("Zeus", "domain", "sky") in asks
    assert not any(subject == "Cronus" and relation == "parent_of" for subject, relation, _obj in asks)
    chains = exact_chains(facts)
    assert ("Uranus", ["parent_of", "is_a"], "titan") in chains
    assert not any(relations == ["parent_of", "domain"] and start == "Cronus" for start, relations, _final in chains)


def test_percentile_matches_the_documented_midpoint():
    from bench.measure_meta import percentile

    assert percentile([1.0, 2.0, 100.0], 50) == 2.0
    assert percentile([1.0, 3.0], 50) == 2.0
    # 100 samples: p50 is the midpoint of sorted indexes 49 and 50.
    sample = [float(i) for i in range(100)]
    assert percentile(sample, 50) == 49.5
