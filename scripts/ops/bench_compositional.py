#!/usr/bin/env python3
"""Compositional generalization benchmark.

Measures whether Resileos returns correct individual facts that compose
into novel answers, versus an LLM that must reason over the same facts
in context.

Two composition modes are tested:

  chain    -- POST /api/v1/chain with forward relations.
              Pure forward traversal only (a -> b -> c).
  compose  -- multiple POST /api/v1/query calls chained in the bench.
              Supports inverse and mixed-direction paths that /chain
              does not.

The composition itself is done outside the store, in the bench. What is
measured is whether the store returns the correct individual facts such
that chaining them yields the correct novel answer. The LLM is given
the same facts in context and asked the same question in natural
language; the comparison is compositional reasoning capability, not
store internals.

If a composition returns 0.0 it means either the store returned wrong
intermediate facts, or a step was ABSTAINED. The per-composition
`last_body_status` and `error` fields show which.

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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from resileos.ui.attach_scale import attach_scale
except ImportError:
    def attach_scale(report):
        return report

OUT = Path("artifacts/report_compositional.json")
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
]

# Composition specs.
#
# kind = "chain":
#     POST /chain with forward relations. The store does the walk.
#
# kind = "compose":
#     Multiple /query calls chained in the bench. Step subjects may be
#     "@prev" to reference the previous step's accepted value.
#
# expected: the composed answer, not an intermediate.

COMPOSITIONS = [
    {
        "kind": "chain",
        "start": "alice",
        "relations": ["parent_of", "parent_of"],
        "expected": "carol",
        "question": "Who is alice's grandchild?",
        "note": "forward 2-hop: alice -> bob -> carol",
        "optional": False,
    },
    {
        "kind": "compose",
        "start": "carol",
        "steps": [
            {"subject": "carol", "relation": "parent_of", "inverse": True},
            {"subject": "@prev", "relation": "parent_of", "inverse": True},
        ],
        "expected": "alice",
        "question": "Who is carol's grandparent?",
        "note": "inverse 2-hop: carol <- bob <- alice",
        "optional": False,
    },
    {
        "kind": "compose",
        "start": "carol",
        "steps": [
            {"subject": "carol", "relation": "parent_of", "inverse": True},
            {"subject": "@prev", "relation": "works_at", "inverse": False},
        ],
        "expected": "globex",
        "question": "Where does carol's parent work?",
        "note": "inverse then forward: carol <- bob -> globex",
        "optional": False,
    },
]


def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    import requests

    r = requests.post(f"{BASE}{path}", json=body, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def seed_base() -> None:
    rows = [[s, r, o] for s, r, o in BASE_FACTS]
    _post("/learn_batch", {"facts": rows}, timeout=60)


def _active() -> list[dict]:
    return [c for c in COMPOSITIONS if not c.get("optional")]


def _run_chain(c: dict) -> tuple[str | None, dict]:
    body = _post("/chain", {"start": c["start"], "relations": c["relations"]})
    return body.get("value"), body


def _run_compose(c: dict) -> tuple[str | None, dict]:
    prev_value: str | None = None
    last_body: dict = {}
    for i, step in enumerate(c["steps"]):
        subj = step["subject"]
        if subj == "@prev":
            if prev_value is None:
                return None, {
                    "error": "prior step returned no value",
                    "step_index": i,
                }
            subj = prev_value
        body = _post("/query", {
            "subject": subj,
            "relation": step["relation"],
            "inverse": step.get("inverse", False),
        })
        last_body = body
        if body.get("status") != "ACCEPTED":
            return None, {
                "error": "intermediate step not ACCEPTED",
                "step_index": i,
                "step_subject": subj,
                "step_relation": step["relation"],
                "step_status": body.get("status"),
                "step_reason": body.get("reason"),
            }
        prev_value = body.get("value")
    return prev_value, last_body


def run_resileos() -> dict:
    seed_base()
    results = []
    hits = 0
    active = _active()

    for c in active:
        t0 = time.perf_counter()
        try:
            if c["kind"] == "chain":
                got, last_body = _run_chain(c)
            elif c["kind"] == "compose":
                got, last_body = _run_compose(c)
            else:
                raise ValueError(f"unknown kind: {c['kind']}")
        except Exception as e:
            got = None
            last_body = {"error": str(e)}
        lat = (time.perf_counter() - t0) * 1000

        ok = (got is not None) and (str(got) == c["expected"])
        if ok:
            hits += 1

        results.append({
            "kind": c["kind"],
            "question": c["question"],
            "expected": c["expected"],
            "got": got,
            "ok": ok,
            "latency_ms": round(lat, 1),
            "note": c["note"],
            "last_body_status": last_body.get("status"),
            "error": last_body.get("error"),
            "error_detail": {
                k: last_body.get(k)
                for k in ("step_index", "step_subject", "step_relation",
                          "step_status", "step_reason")
                if k in last_body
            } or None,
        })

    return {
        "composition_rate": round(hits / len(active), 4) if active else 0.0,
        "hits": hits,
        "total": len(active),
        "results": results,
    }


def run_inprocess() -> dict:
    """Same three compositions against Titanos.ask / ask_inverse / chain.

    Does not open a socket. Inverse hops call ``ask_inverse``. Forward
    hops and ``/chain`` call ``ask`` / ``chain``. A step counts only
    when the answer status is ACCEPTED.
    """
    from titanos import Titanos, TitanosConfig

    titan = Titanos(TitanosConfig())
    for subject, relation, obj in BASE_FACTS:
        titan.learn(subject, relation, obj)

    def _accepted(answer) -> str | None:
        if getattr(answer, "status", None) != "ACCEPTED":
            return None
        value = getattr(answer, "value", None)
        return None if value is None else str(value)

    results = []
    hits = 0
    active = _active()
    for spec in active:
        started = time.perf_counter()
        error = None
        got = None
        try:
            if spec["kind"] == "chain":
                got = _accepted(titan.chain(spec["start"], spec["relations"]))
            elif spec["kind"] == "compose":
                prev = None
                for index, step in enumerate(spec["steps"]):
                    subject = step["subject"]
                    if subject == "@prev":
                        if prev is None:
                            error = "prior step returned no value"
                            got = None
                            break
                        subject = prev
                    if step.get("inverse"):
                        answer = titan.ask_inverse(subject, step["relation"])
                    else:
                        answer = titan.ask(subject, step["relation"])
                    got = _accepted(answer)
                    if got is None:
                        error = f"step {index} not ACCEPTED"
                        break
                    prev = got
            else:
                raise ValueError(f"unknown kind: {spec['kind']}")
        except Exception as exc:
            got = None
            error = type(exc).__name__
        elapsed = (time.perf_counter() - started) * 1000
        ok = got is not None and str(got) == spec["expected"]
        if ok:
            hits += 1
        results.append(
            {
                "kind": spec["kind"],
                "question": spec["question"],
                "expected": spec["expected"],
                "got": got,
                "ok": ok,
                "latency_ms": round(elapsed, 1),
                "note": spec["note"],
                "error": error,
            }
        )
    return {
        "transport": "in-process Titanos.ask / ask_inverse / chain",
        "backend": "titanos",
        "config": "Titanos(TitanosConfig())",
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
        import requests

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
    active = _active()

    for c in active:
        q = c["question"]
        t0 = time.perf_counter()
        try:
            ans = ask(q)
        except Exception as e:
            ans = f"<error: {e}>"
        lat = (time.perf_counter() - t0) * 1000

        ok = c["expected"].lower() in ans.lower()
        if ok:
            hits += 1

        results.append({
            "question": q,
            "expected": c["expected"],
            "got": ans,
            "ok": ok,
            "latency_ms": round(lat, 1),
            "note": c["note"],
        })

    return {
        "model": LLM_MODEL,
        "composition_rate": round(hits / len(active), 4) if active else 0.0,
        "hits": hits,
        "total": len(active),
        "results": results,
    }


def main() -> int:
    from bench.measure_meta import environment, redact_text, utc_now

    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-seed", action="store_true")
    ap.add_argument(
        "--in-process",
        action="store_true",
        help="score Titanos directly and do not call HTTP",
    )
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "measured_at": utc_now(),
        "environment": environment(),
        "base_facts": [list(row) for row in BASE_FACTS],
        "compositions": COMPOSITIONS,
    }

    if args.in_process:
        report["http"] = {
            "status": "skipped",
            "reason": "--in-process set; no HTTP server was called",
        }
        try:
            report["resileos"] = run_inprocess()
        except Exception as exc:
            report["resileos"] = {"error": type(exc).__name__}
        report["llm"] = None
        report["llm_note"] = "LLM leg not called on the in-process path"
    else:
        if not args.skip_seed:
            try:
                seed_base()
            except Exception as e:
                report["seed_error"] = redact_text(str(e))

        try:
            report["resileos"] = run_resileos()
        except Exception as e:
            report["resileos"] = {"error": redact_text(str(e))}

        llm = run_llm()
        report["llm"] = llm

    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = redact_text(json.dumps(attach_scale(report), indent=2)) + "\n"
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
