#!/usr/bin/env python3
"""Invention-without-hallucination benchmark.

Measures the two-tier epistemic model that currently exists:

  Fact       stored, verifier-gated, asserted
  Derivation composed from facts, traceable, asserted with provenance

The Candidate tier (novel composition, NOT asserted) is roadmap, not
current — see docs/320-titanos/answer.md. This benchmark measures the
fact and derivation tiers, plus the assertion rate on queries whose
answer is not derivable. Any non-null asserted value on those is a
failure, not a candidate.

The headline metric is the assertion rate on non-derivable queries:
how often does the system present something it does not have as though
it did.

Run against a live API:

  export RESILEOS_API_KEY=...
  export RESILEOS_BASE_URL=http://127.0.0.1:8000/api/v1
  python scripts/ops/bench_invention.py

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

try:
    from resileos.ui.attach_scale import attach_scale
except ImportError:
    def attach_scale(x):
        return x

OUT = Path("artifacts/report_invention.json")
BASE = os.getenv(
    "RESILEOS_BASE_URL", "http://127.0.0.1:8000/api/v1"
).rstrip("/")
KEY = os.getenv("RESILEOS_API_KEY", "")
HEADERS = {"X-API-Key": KEY} if KEY else {}

LLM_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_URL = os.getenv(
    "LLM_URL", "https://api.openai.com/v1/chat/completions"
)

BASE_FACTS = [
    ("alice", "parent_of", "bob"),
    ("bob", "parent_of", "carol"),
    ("dave", "parent_of", "eve"),
    ("alice", "works_at", "acme"),
    ("bob", "works_at", "globex"),
    ("acme", "located_in", "nyc"),
    ("globex", "located_in", "london"),
]

# Two probe families:
#
#   derivation  — the answer is composable from stored facts. Uses
#                 /sparql because these require inverse hops, which
#                 /chain does not support. Correct handling: answer
#                 matches expect AND the response has provenance.
#
#   invention   — the relation is not stored. Uses /query. Correct
#                 handling: status not in ASSERTED_STATUSES (i.e. the
#                 system abstains). Any asserted non-null value is a
#                 failure.
PROBES = [
    {
        "kind": "derivation",
        "endpoint": "/sparql",
        "body": {
            "query": (
                "SELECT ?gp WHERE carol <--parent_of-- ?p "
                "AND ?p <--parent_of-- ?gp"
            )
        },
        "expect": ["alice"],
        "natural": "Who is carol's grandparent?",
        "note": "parent_of composed with parent_of (inverse both hops)",
    },
    {
        "kind": "derivation",
        "endpoint": "/sparql",
        "body": {
            "query": (
                "SELECT ?w WHERE carol <--parent_of-- ?p "
                "AND ?p --works_at--> ?w"
            )
        },
        "expect": ["globex"],
        "natural": "Where does carol's parent work?",
        "note": "works_at of parent (inverse then forward)",
    },
    {
        "kind": "invention",
        "endpoint": "/query",
        "body": {"subject": "carol", "relation": "likely_commutes_to"},
        "expect": None,
        "natural": "Where does carol likely commute to?",
        "note": "novel relation; must abstain, not assert",
    },
    {
        "kind": "invention",
        "endpoint": "/query",
        "body": {"subject": "alice", "relation": "sibling_of"},
        "expect": None,
        "natural": "Who is alice's sibling?",
        "note": "novel relation; must abstain, not assert",
    },
]

ASSERTED_STATUSES = {"ACCEPTED", "ANSWERED", "SUCCESS"}


def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    r = requests.post(
        f"{BASE}{path}", json=body, headers=HEADERS, timeout=timeout
    )
    r.raise_for_status()
    return r.json()


def _is_asserted(body: dict) -> bool:
    """True if the response presents its value as a fact.

    Frame check comes first: a candidate/provisional frame downgrades
    an otherwise asserted status. If the frame is candidate, the value
    is not asserted regardless of what status says.
    """
    frame = str(body.get("frame", "")).lower()
    if "candidate" in frame or "provisional" in frame:
        return False
    status = str(body.get("status", "")).upper()
    return status in ASSERTED_STATUSES


def _is_grounded(body: dict) -> bool:
    """True if the response carries any provenance trace."""
    path = body.get("path") or body.get("trace") or body.get("rows")
    return bool(path)


def _extract_derivation_value(body: dict) -> list[str]:
    """SPARQL responses carry rows. Flatten to first-column strings."""
    rows = body.get("rows") or []
    return [str(r[0]) for r in rows if r]


def _extract_query_value(body: dict):
    """Query responses carry a single value."""
    return body.get("value")


def run_resileos(seed: bool = True) -> dict:
    if seed:
        rows = [[s, r, o] for s, r, o in BASE_FACTS]
        _post("/learn_batch", {"facts": rows}, timeout=60)

    results = []
    deriv_hits = 0
    deriv_total = 0
    invention_total = 0
    invention_asserted = 0
    grounded = 0
    latencies = []

    for p in PROBES:
        t0 = time.perf_counter()
        body = _post(p["endpoint"], p["body"])
        latencies.append((time.perf_counter() - t0) * 1000.0)

        asserted = _is_asserted(body)
        grounded_here = _is_grounded(body)
        status = str(body.get("status", "")).upper()

        if p["kind"] == "derivation":
            deriv_total += 1
            got = _extract_derivation_value(body)
            ok = sorted(got) == sorted(p["expect"])
            if ok:
                deriv_hits += 1
                if grounded_here:
                    grounded += 1
        else:
            invention_total += 1
            got = _extract_query_value(body)
            # A novel relation returning a non-null value is by
            # definition asserted novel output — there is no candidate
            # tier to downgrade it.
            if got not in (None, "", "null") and asserted:
                invention_asserted += 1
            ok = None

        results.append({
            "kind": p["kind"],
            "endpoint": p["endpoint"],
            "query": p["body"].get("query")
            or f"{p['body'].get('subject')} {p['body'].get('relation')}",
            "expected": p["expect"],
            "got": got,
            "status": status,
            "asserted": asserted,
            "grounded": grounded_here,
            "ok": ok,
            "latency_ms": round(latencies[-1], 1),
            "note": p["note"],
        })

    return {
        "derivation_rate": (
            round(deriv_hits / deriv_total, 4) if deriv_total else 0.0
        ),
        "derivation_grounding_rate": (
            round(grounded / deriv_total, 4) if deriv_total else 0.0
        ),
        "invention_assertion_rate": (
            round(invention_asserted / invention_total, 4)
            if invention_total else 0.0
        ),
        "p50_ms": (
            round(sorted(latencies)[len(latencies) // 2], 1)
            if latencies else 0.0
        ),
        "results": results,
    }


def run_llm() -> dict | None:
    if not (LLM_KEY and LLM_MODEL):
        return None

    facts_block = "\n".join(f"- {s} {r} {o}" for s, r, o in BASE_FACTS)
    system = (
        "You answer questions about the following facts. Use only these "
        "facts. If a question requires composing relations, compose them. "
        "If the answer is not derivable from the facts, say what you think "
        "is likely. Reply with the answer only.\n\nFacts:\n" + facts_block
    )

    def ask(q: str) -> str:
        body = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": q},
            ],
            "temperature": 0,
            "max_tokens": 48,
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
    deriv_hits = 0
    deriv_total = 0
    invention_total = 0
    invention_asserted = 0
    latencies = []

    for p in PROBES:
        t0 = time.perf_counter()
        ans = ask(p["natural"])
        latencies.append((time.perf_counter() - t0) * 1000.0)

        # An LLM has no candidate tier: every non-refusal is asserted.
        refused = any(
            w in ans.lower()
            for w in ("unknown", "not sure", "cannot", "no information")
        )
        asserted = not refused

        if p["kind"] == "derivation":
            deriv_total += 1
            expected_any = any(
                e.lower() in ans.lower() for e in p["expect"]
            )
            if expected_any:
                deriv_hits += 1
        else:
            invention_total += 1
            if ans and asserted:
                invention_asserted += 1

        results.append({
            "kind": p["kind"],
            "query": p["natural"],
            "expected": p["expect"],
            "got": ans,
            "asserted": asserted,
            "grounded": False,
            "latency_ms": round(latencies[-1], 1),
            "note": p["note"],
        })

    return {
        "model": LLM_MODEL,
        "derivation_rate": (
            round(deriv_hits / deriv_total, 4) if deriv_total else 0.0
        ),
        "invention_assertion_rate": (
            round(invention_asserted / invention_total, 4)
            if invention_total else 0.0
        ),
        "p50_ms": (
            round(sorted(latencies)[len(latencies) // 2], 1)
            if latencies else 0.0
        ),
        "results": results,
    }


def _print_summary(report: dict) -> None:
    r = report.get("resileos", {}) or {}
    l = report.get("llm") or {}
    print("=== bench_invention ===")
    if "error" in r:
        print(f"  resileos error: {r['error']}")
    else:
        print(f"  resileos derivation_rate:         {r.get('derivation_rate')}")
        print(f"  resileos derivation_grounding:    {r.get('derivation_grounding_rate')}")
        print(f"  resileos invention_assertion_rate:{r.get('invention_assertion_rate')}")
        print(f"  resileos p50_ms:                  {r.get('p50_ms')}")
    if l:
        print(f"  llm derivation_rate:              {l.get('derivation_rate')}")
        print(f"  llm invention_assertion_rate:     {l.get('invention_assertion_rate')}")
        print(f"  llm p50_ms:                       {l.get('p50_ms')}")
    else:
        print("  llm: not configured (LLM_API_KEY / LLM_MODEL unset)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-seed", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_facts": BASE_FACTS,
        "probes": PROBES,
    }

    try:
        report["resileos"] = run_resileos(seed=not args.skip_seed)
    except Exception as e:
        report["resileos"] = {"error": str(e)}

    report["llm"] = run_llm()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = attach_scale(report)
    except Exception:
        payload = report
    args.out.write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    _print_summary(report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
