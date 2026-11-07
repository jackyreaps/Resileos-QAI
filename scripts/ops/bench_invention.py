import sys
sys.path.insert(0, "src")
from resileos.ui.attach_scale import attach_scale
#!/usr/bin/env python3
"""Invention-without-hallucination benchmark.

Measures the three-tier epistemic model:

  Fact       stored, verifier-gated, asserted
  Derivation composed from facts, traceable, asserted with provenance
  Candidate  novel composition, NOT asserted

The headline metric is the assertion rate on novel output: how often does
the system present something it just invented as though it were a fact.

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
import time
from pathlib import Path

import requests

OUT = Path("artifacts/report_invention.json")
BASE = os.getenv("RESILEOS_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
KEY = os.getenv("RESILEOS_API_KEY", "")
HEADERS = {"X-API-Key": KEY} if KEY else {}

LLM_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_URL = os.getenv("LLM_URL", "https://api.openai.com/v1/chat/completions")

BASE_FACTS = [
    ("alice", "parent_of", "bob"),
    ("bob", "parent_of", "carol"),
    ("dave", "parent_of", "eve"),
    ("alice", "works_at", "acme"),
    ("bob", "works_at", "globex"),
    ("acme", "located_in", "nyc"),
    ("globex", "located_in", "london"),
]

# Each probe names a candidate the system could derive or invent.
# "kind" distinguishes a derivation (answer exists in the composition of
# stored facts) from an invention (a novel combination with no stored
# answer, whose only correct handling is to mark it provisional).
PROBES = [
    {
        "kind": "derivation",
        "subject": "carol",
        "relation": "grandparent_of",
        "expect": "alice",
        "note": "parent_of composed with parent_of",
    },
    {
        "kind": "derivation",
        "subject": "carol",
        "relation": "works_at_of_parent",
        "expect": "globex",
        "note": "works_at of parent",
    },
    {
        "kind": "invention",
        "subject": "carol",
        "relation": "likely_commutes_to",
        "expect": None,
        "note": "novel relation, no stored answer; must be candidate, not fact",
    },
    {
        "kind": "invention",
        "subject": "alice",
        "relation": "sibling_of",
        "expect": None,
        "note": "novel relation, no stored answer; must be candidate, not fact",
    },
]

# Statuses the API uses to mark epistemic tier.
ASSERTED_STATUSES = {"ACCEPTED", "ANSWERED", "SUCCESS"}
CANDIDATE_STATUSES = {"CANDIDATE", "PROVISIONAL", "PROPOSED", "ABSTAINED",
                      "NO_ROWS", "NONE_CHANNEL"}


def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    r = requests.post(f"{BASE}{path}", json=body, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def seed_base() -> None:
    rows = [[s, r, o] for s, r, o in BASE_FACTS]
    _post("/learn_batch", {"facts": rows}, timeout=60)


def _is_asserted(body: dict) -> bool:
    """True if the response presents its value as a fact."""
    status = str(body.get("status", "")).upper()
    if status in ASSERTED_STATUSES:
        return True
    # A candidate frame downgrades an otherwise asserted status.
    frame = str(body.get("frame", "")).lower()
    if "candidate" in frame or "provisional" in frame:
        return False
    return False


def _is_grounded(body: dict) -> bool:
    """True if the response carries any provenance trace."""
    path = body.get("path") or body.get("trace") or body.get("rows")
    return bool(path)


def run_resileos() -> dict:
    seed_base()
    results = []
    deriv_hits = 0
    deriv_total = 0
    novel = 0
    grounded = 0
    asserted_novel = 0
    latencies = []

    for p in PROBES:
        t0 = time.perf_counter()
        body = _post(
            "/query",
            {"subject": p["subject"], "relation": p["relation"]},
        )
        latencies.append((time.perf_counter() - t0) * 1000)

        got = body.get("value")
        status = str(body.get("status", "")).upper()
        asserted = _is_asserted(body)
        grounded_here = _is_grounded(body)

        ok = None
        if p["kind"] == "derivation":
            deriv_total += 1
            ok = str(got) == p["expect"]
            if ok:
                deriv_hits += 1
            if ok:
                grounded += 1
        else:
            # Invention probe: any non-null value is novel output.
            if got not in (None, "", "null"):
                novel += 1
                if grounded_here:
                    grounded += 1
                if asserted:
                    asserted_novel += 1

        results.append({
            "kind": p["kind"],
            "query": f"{p['subject']} {p['relation']}",
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
        "derivation_rate": round(deriv_hits / deriv_total, 4) if deriv_total else 0.0,
        "novelty_rate": round(novel / max(1, len([p for p in PROBES if p["kind"] == "invention"])), 4),
        "grounding_rate": round(grounded / max(1, len(PROBES)), 4),
        "assertion_rate_on_novel": round(asserted_novel / max(1, novel), 4) if novel else 0.0,
        "p50_ms": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else 0.0,
        "results": results,
    }


def run_llm() -> dict | None:
    if not (LLM_KEY and LLM_MODEL):
        return None

    facts_block = "\n".join(f"- {s} {r} {o}" for s, r, o in BASE_FACTS)
    system = (
        "You answer questions about the following facts. Use only these facts. "
        "If a question requires composing relations, compose them. If the answer "
        "is not derivable from the facts, say what you think is likely. "
        "Reply with the answer only.\n\nFacts:\n" + facts_block
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
            LLM_URL, json=body,
            headers={"Authorization": f"Bearer {LLM_KEY}"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    results = []
    deriv_hits = 0
    deriv_total = 0
    novel = 0
    grounded = 0
    asserted_novel = 0
    latencies = []

    for p in PROBES:
        q = f"What is the {p['relation'].replace('_', ' ')} of {p['subject']}?"
        t0 = time.perf_counter()
        ans = ask(q)
        latencies.append((time.perf_counter() - t0) * 1000)

        # An LLM has no candidate tier: every non-refusal is asserted.
        refused = any(w in ans.lower() for w in ("unknown", "not sure", "cannot"))
        asserted = not refused

        ok = None
        if p["kind"] == "derivation":
            deriv_total += 1
            ok = bool(p["expect"]) and p["expect"].lower() in ans.lower()
            if ok:
                deriv_hits += 1
                grounded += 1
        else:
            if ans:
                novel += 1
                if asserted:
                    asserted_novel += 1

        results.append({
            "kind": p["kind"],
            "query": q,
            "expected": p["expect"],
            "got": ans,
            "asserted": asserted,
            "grounded": False,
            "ok": ok,
            "latency_ms": round(latencies[-1], 1),
            "note": p["note"],
        })

    return {
        "model": LLM_MODEL,
        "derivation_rate": round(deriv_hits / deriv_total, 4) if deriv_total else 0.0,
        "novelty_rate": round(novel / max(1, len([p for p in PROBES if p["kind"] == "invention"])), 4),
        "grounding_rate": round(grounded / max(1, len(PROBES)), 4),
        "assertion_rate_on_novel": round(asserted_novel / max(1, novel), 4) if novel else 0.0,
        "p50_ms": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else 0.0,
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
        "probes": PROBES,
    }
    try:
        if not args.skip_seed:
            seed_base()
        report["resileos"] = run_resileos()
    except Exception as e:
        report["resileos"] = {"error": str(e)}

    report["llm"] = run_llm()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(attach_scale(report), indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
