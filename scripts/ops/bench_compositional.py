#!/usr/bin/env python3
"""Compositional generalization benchmark.

Measures whether Resileos can answer novel combinations of known relations
by algebraic composition (VSA bind/unbind or chain), versus an LLM that
must reason over the same facts in context.

Example:
  Known: alice parent_of bob; bob parent_of carol
  Query: carol grandparent_of  ->  alice

Run against a live API:
  export RESILEOS_API_KEY=...
  export RESILEOS_BASE_URL=http://127.0.0.1:8000/api/v1
  python scripts/ops/bench_compositional.py

Optional LLM baseline (auto-detected):
  export LLM_API_KEY=...
  export LLM_MODEL=gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

import requests

from resileos.ui.attach_scale import attach_scale

OUT = Path("artifacts/report_compositional.json")
BASE = os.getenv("RESILEOS_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
KEY = os.getenv("RESILEOS_API_KEY", "")
HEADERS = {"X-API-Key": KEY} if KEY else {}

LLM_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_URL = os.getenv("LLM_URL", "https://api.openai.com/v1/chat/completions")

# Base facts that will be seeded
BASE_FACTS = [
    ("alice", "parent_of", "bob"),
    ("bob", "parent_of", "carol"),
    ("dave", "parent_of", "eve"),
    ("alice", "works_at", "acme"),
    ("bob", "works_at", "globex"),
]

# Novel compositions the store should be able to answer if composition works.
# The third element is the expected value.
# The fourth element is a note. If a composition is not implemented in the
# store (e.g. sibling_of), mark it "optional": True so it does not drag the
# composition rate down for reasons unrelated to the algebra claim.
COMPOSITIONS = [
    {
        "subject": "carol",
        "relation": "grandparent_of",
        "expected": "alice",
        "note": "parent_of ∘ parent_of",
        "optional": False,
    },
    {
        "subject": "bob",
        "relation": "sibling_of",
        "expected": "eve",
        "note": "shared parent_of dave (only if sibling_of is implemented)",
        "optional": True,
    },
    {
        "subject": "carol",
        "relation": "works_at_of_parent",
        "expected": "globex",
        "note": "works_at of parent",
        "optional": False,
    },
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


def _active_compositions() -> list[dict]:
    return [c for c in COMPOSITIONS if not c.get("optional")]


def run_resileos() -> dict:
    seed_base()
    results = []
    hits = 0
    active = _active_compositions()
    for c in active:
        t0 = time.perf_counter()
        body = query(c["subject"], c["relation"])
        lat = (time.perf_counter() - t0) * 1000
        got = body.get("value")
        ok = str(got) == c["expected"]
        if ok:
            hits += 1
        results.append(
            {
                "query": f"{c['subject']} {c['relation']}",
                "expected": c["expected"],
                "got": got,
                "status": body.get("status"),
                "ok": ok,
                "latency_ms": round(lat, 1),
                "note": c["note"],
            }
        )
    return {
        "composition_rate": round(hits / len(active), 4) if active else 0.0,
        "hits": hits,
        "total": len(active),
        "results": results,
    }


def run_llm() -> dict | None:
    if not (LLM_KEY and LLM_MODEL):
        return None

    facts_block = "\n".join(f"- {s} {r} {o}" for s, r, o in BASE_FACTS)
    system = (
        "You answer questions about the following facts. Use only these "
        "facts. If a question requires composing relations, compose them. "
        "Reply with the answer only, or the word UNKNOWN.\n\nFacts:\n"
        + facts_block
    )

    def ask(q: str) -> str:
        body = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": q},
            ],
            "temperature": 0,
            "max_tokens": 32,
        }
        r = requests.post(
            LLM_URL,
            json=body,
            headers={"Authorization": f"Bearer {LLM_KEY}"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    results = []
    hits = 0
    active = _active_compositions()
    for c in active:
        q = f"What is the {c['relation'].replace('_', ' ')} of {c['subject']}?"
        t0 = time.perf_counter()
        ans = ask(q)
        lat = (time.perf_counter() - t0) * 1000
        ok = c["expected"].lower() in ans.lower()
        if ok:
            hits += 1
        results.append(
            {
                "query": q,
                "expected": c["expected"],
                "got": ans,
                "ok": ok,
                "latency_ms": round(lat, 1),
                "note": c["note"],
            }
        )
    return {
        "model": LLM_MODEL,
        "composition_rate": round(hits / len(active), 4) if active else 0.0,
        "hits": hits,
        "total": len(active),
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-seed", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    report: dict = {
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

    llm = run_llm()
    report["llm"] = llm

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(attach_scale(report), indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
