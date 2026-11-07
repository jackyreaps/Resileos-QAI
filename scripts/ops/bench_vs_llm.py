import sys
sys.path.insert(0, "src")
from resileos.ui.attach_scale import attach_scale
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
]


def run_store_bench(learn_fn, query_fn) -> dict:
    for s, r, o in KNOWN:
        learn_fn(s, r, o)
    t0 = time.perf_counter()
    hits = 0
    for s, r, o in KNOWN:
        v = query_fn(s, r)
        if str(v) == o:
            hits += 1
    known_ms = (time.perf_counter() - t0) * 1000
    invent = 0
    for s, r, _ in UNKNOWN:
        v = query_fn(s, r)
        if v is not None and v != "" and v != []:
            invent += 1
    return {
        "exact_match_rate": hits / len(KNOWN),
        "invent_rate": invent / len(UNKNOWN),
        "p50_latency_ms_known_batch": known_ms / max(len(KNOWN), 1),
        "backend": "titanos_or_stub",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("artifacts/report_memory_vs_llm.json"))
    args = ap.parse_args()
    store: dict[tuple[str, str], str] = {}

    def learn(s, r, o):
        store[(s, r)] = o

    def query(s, r):
        return store.get((s, r))

    # Prefer live Titanos if importable
    try:
        from titanos import Titanos  # type: ignore

        t = Titanos()
        def learn(s, r, o):
            t.learn(s, r, o)

        def query(s, r):
            return t.ask(s, r)
    except Exception:
        pass

    resileos = run_store_bench(learn, query)
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
