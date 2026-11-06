#!/usr/bin/env python3
"""
Compositional generalization benchmark.

Measures whether Resileos can answer novel combinations of known relations
by algebraic composition (VSA bind/unbind or simple chain), versus an LLM
that must reason over the same facts in context.

Example:
  Known: alice parent_of bob
         bob parent_of carol
  Query: sibling_of(alice)  or  grandparent_of(carol)

Run against a live API:
  export RESILEOS_API_KEY=...
  export RESILEOS_BASE_URL=http://127.0.0.1:8000/api/v1
  python scripts/ops/bench_compositional.py
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests

OUT = Path("artifacts/report_compositional.json")
BASE = os.getenv("RESILEOS_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
KEY = os.getenv("RESILEOS_API_KEY", "")
HEADERS = {"X-API-Key": KEY} if KEY else {}

# Base facts that will be seeded
BASE_FACTS = [
    ("alice", "parent_of", "bob"),
    ("bob", "parent_of", "carol"),
    ("dave", "parent_of", "eve"),
    ("alice", "works_at", "acme"),
    ("bob", "works_at", "globex"),
]

# Novel compositions the store should be able to answer if composition works
COMPOSITIONS = [
    # (query_subject, query_relation, expected_value, explanation)
    ("carol", "grandparent_of", "alice", "parent_of ∘ parent_of"),
    ("bob", "sibling_of", "eve", "shared parent_of dave (if implemented)"),
    ("carol", "works_at_of_parent", "globex", "works_at of parent"),
]

def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    r = requests.post(f"{BASE}{path}", json=body, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def seed_base() -> None:
    rows = [[s, r, o] for s, r, o in BASE_FACTS]
    _post("/learn_batch", {"facts": rows}, timeout=60)


def query(subject: str, relation: str) -> dict:
    return _post("/query", {"subject": subject, "relation": relation})


def run_resileos() -> dict:
    seed_base()
    results = []
    hits = 0
    for subj, rel, expected, note in COMPOSITIONS:
        t0 = time.perf_counter()
        body = query(subj, rel)
        lat = (time.perf_counter() - t0) * 1000
        got = body.get("value")
        ok = str(got) == expected
        if ok:
            hits += 1
        results.append({
            "query": f"{subj} {rel}",
            "expected": expected,
            "got": got,
            "status": body.get("status"),
            "ok": ok,
            "latency_ms": round(lat, 1),
            "note": note,
        })
    return {
        "composition_rate": round(hits / len(COMPOSITIONS), 4) if COMPOSITIONS else 0.0,
        "hits": hits,
        "total": len(COMPOSITIONS),
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-seed", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_facts": BASE_FACTS,
        "compositions": COMPOSITIONS,
    }
    try:
        if not args.skip_seed:
            seed_base()
        report["resileos"] = run_resileos()
    except Exception as e:
        report["resileos"] = {"error": str(e)}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
