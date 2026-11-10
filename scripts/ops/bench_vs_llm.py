#!/usr/bin/env python3
"""
Exact-memory benchmark harness (Resileos vs optional LLM baseline).

Does not require GPU. LLM baseline is optional via env:
  BENCH_LLM_URL  POST JSON {prompt} -> {text}
  BENCH_LLM_KEY  optional bearer

Usage:
  PYTHONPATH=src python scripts/ops/bench_vs_llm.py --out artifacts/report_memory_vs_llm.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
import sys
sys.path.insert(0, "src")
from resileos.ui.attach_scale import attach_scale

# Known facts for exact-match; unknowns for invent-rate
KNOWN = [
    ("Zeus", "domain", "sky"),
    ("Poseidon", "domain", "sea"),
    ("Athena", "domain", "wisdom"),
]
UNKNOWN = [
    ("Zeus", "ssn", None),
    ("Alice", "works_at", None),
    ("Acme", "secret_key", None),
    ("Poseidon", "ssn", None),
    ("Athena", "password", None),
    ("Hera", "api_key", None),
    ("Ares", "credit_card", None),
    ("Apollo", "private_key", None),
    ("Artemis", "bank_pin", None),
    ("Hermes", "ssn", None),
    ("Hades", "password", None),
    ("Demeter", "api_key", None),
]


def median(values: list[float]) -> float:
    """Midpoint of the sorted sample. Even counts average the two middle values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float(ordered[mid - 1] + ordered[mid]) / 2.0


def run_store_bench(learn_fn, query_fn, *, backend: str) -> dict:
    for s, r, o in KNOWN:
        learn_fn(s, r, o)
    hits = 0
    latencies = []
    for s, r, o in KNOWN:
        t0 = time.perf_counter()
        v = query_fn(s, r)
        latencies.append((time.perf_counter() - t0) * 1000)
        if str(v) == o:
            hits += 1
    invent = 0
    for s, r, _ in UNKNOWN:
        v = query_fn(s, r)
        if v is not None and v != "" and v != []:
            invent += 1
    return {
        "exact_match_rate": hits / len(KNOWN),
        "invent_rate": invent / len(UNKNOWN),
        "p50_latency_ms_known": median(latencies),
        "mean_latency_ms_known": sum(latencies) / max(len(latencies), 1),
        "backend": backend,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("artifacts/report_memory_vs_llm.json"))
    args = ap.parse_args()
    store: dict[tuple[str, str], str] = {}
    backend = "dict_stub"

    def learn(s, r, o):
        store[(s, r)] = o

    def query(s, r):
        return store.get((s, r))

    # Prefer live Titanos if importable. Titanos() requires a config.
    try:
        from titanos import Titanos, TitanosConfig  # type: ignore

        t = Titanos(TitanosConfig())

        def learn(s, r, o):
            t.learn(s, r, o)

        def query(s, r):
            ans = t.ask(s, r)
            return getattr(ans, "value", ans)

        backend = "titanos"
    except Exception as exc:
        print(f"bench: Titanos unavailable ({exc}); using dict stub")

    resileos = run_store_bench(learn, query, backend=backend)
    llm = {
        "exact_match_rate": None,
        "invent_rate": None,
        "note": "Set BENCH_LLM_URL to fill LLM baseline",
    }
    url = os.getenv("BENCH_LLM_URL", "").strip()
    if url:
        import urllib.request

        invent = 0
        for s, r, _ in UNKNOWN:
            prompt = f"Answer with only the object value if known, else say UNKNOWN: {s} {r}"
            req = urllib.request.Request(
                url,
                data=json.dumps({"prompt": prompt}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            key = os.getenv("BENCH_LLM_KEY", "")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    text = json.loads(resp.read().decode()).get("text", "")
                if text and "UNKNOWN" not in text.upper():
                    invent += 1
            except Exception:
                invent += 1  # treat failure as non-abstain for conservative baseline
        llm = {
            "invent_rate": invent / len(UNKNOWN),
            "exact_match_rate": None,
            "backend": url,
        }

    report = {
        "resileos": resileos,
        "llm_baseline": llm,
        "thesis": "Invent rate on unknown facts should be 0 for Resileos; LLM baseline often > 0.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(attach_scale(report), indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
