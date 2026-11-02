#!/usr/bin/env python3
"""RES-332 ops metrics probe.

Measures M1-M5 against a running Resileos-QAI instance over HTTP.

  M1  tool honesty        known fact turns answered from the store, not invented
  M2  invention rate      unknown fact turns abstain / NO_ROWS, not fabricated
  M3  latency / capacity  per-endpoint p50/p95 and store size
  M4  hub durability      hub facts survive /save + restart (two-phase run)
  M5  scale snapshot      current facts, entities, and response shape

Usage:
  # phase 1: learn corpus, save, print baseline
  RESILEOS_API_KEY=... python scripts/ops/run_ops_metrics.py --phase learn

  # restart the container here

  # phase 2: re-query, verify hub facts survived
  RESILEOS_API_KEY=... python scripts/ops/run_ops_metrics.py --phase verify

  # one-shot (no restart test)
  RESILEOS_API_KEY=... python scripts/ops/run_ops_metrics.py --phase both
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import requests

BASE = os.getenv("RESILEOS_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
KEY = os.getenv("RESILEOS_API_KEY", "").strip()
HEADERS = {"X-API-Key": KEY} if KEY else {}
OUT = Path("artifacts/report_ops_metrics.json")

# Fixed corpus. Keep this small and stable; it is a probe, not a benchmark.
KNOWN = [
    ("alice", "knows", "bob"),
    ("bob", "knows", "carol"),
    ("bob", "works_at", "acme"),
    ("acme", "located_in", "nyc"),
    ("carol", "works_at", "globex"),
]

HUB_USER = "user:probe_hub"
HUB_FACTS = [
    (HUB_USER, "prefers", "dark_mode"),
    (HUB_USER, "timezone", "utc-5"),
    (HUB_USER, "language", "en"),
]

UNKNOWN = [
    ("zoe", "knows", "alice"),
    ("acme", "ceo", "unknown-person"),
]


def _post(path: str, payload: dict, timeout: float = 30.0) -> requests.Response:
    return requests.post(
        f"{BASE}{path}", json=payload, headers=HEADERS, timeout=timeout
    )


def _get(path: str, timeout: float = 10.0) -> requests.Response:
    return requests.get(f"{BASE}{path}", headers=HEADERS, timeout=timeout)


def _check(resp: requests.Response, label: str) -> dict:
    if resp.status_code != 200:
        raise SystemExit(f"{label} failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def _learn(facts: list[tuple[str, str, str]]) -> int:
    rows = [[s, r, o] for s, r, o in facts]
    body = _check(_post("/learn_batch", {"facts": rows}, timeout=120), "learn_batch")
    return int(body.get("added", 0))


def _timed_query(subject: str, relation: str, inverse: bool = False) -> tuple[dict, float]:
    t0 = time.perf_counter()
    body = _check(
        _post("/query", {"subject": subject, "relation": relation, "inverse": inverse}),
        f"query {subject} {relation}",
    )
    return body, (time.perf_counter() - t0) * 1000.0


def _timed_answer(subject: str, relation: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    body = _check(
        _post("/answer", {"subject": subject, "relation": relation}),
        f"answer {subject} {relation}",
    )
    return body, (time.perf_counter() - t0) * 1000.0


def _stats() -> dict:
    return _check(_get("/stats"), "stats")


def _substrate_stats() -> dict:
    return _check(_get("/substrate_stats"), "substrate_stats")


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(round(p * (len(values) - 1))))
    return round(values[idx], 2)


def phase_learn() -> dict:
    added = _learn(KNOWN)
    hub_added = _learn(HUB_FACTS)
    _check(_post("/save", {}), "save")
    return {
        "learned_known": added,
        "learned_hub": hub_added,
        "stats_after_learn": _stats(),
        "substrate_after_learn": _substrate_stats(),
    }


def phase_verify() -> dict:
    # M1: known fact turns must be answered from the store.
    m1_rows = []
    m1_lat = []
    for s, r, _o in KNOWN:
        body, ms = _timed_query(s, r)
        m1_lat.append(ms)
        m1_rows.append(
            {
                "subject": s,
                "relation": r,
                "status": body.get("status"),
                "value": body.get("value"),
                "loops": body.get("loops"),
                "child_name": body.get("child_name"),
                "latency_ms": round(ms, 2),
            }
        )
    m1_honest = sum(1 for x in m1_rows if x["status"] == "ACCEPTED")
    m1_rate = round(m1_honest / max(1, len(m1_rows)), 4)

    # M2: unknown fact turns must not fabricate.
    m2_rows = []
    for s, r in UNKNOWN:
        body, ms = _timed_query(s, r)
        m2_rows.append(
            {
                "subject": s,
                "relation": r,
                "status": body.get("status"),
                "value": body.get("value"),
                "latency_ms": round(ms, 2),
            }
        )
    m2_invented = sum(
        1 for x in m2_rows if x["status"] == "ACCEPTED" and x.get("value")
    )
    m2_invention_rate = round(m2_invented / max(1, len(m2_rows)), 4)

    # M3: latency + capacity snapshot.
    answer_lat = []
    for s, r, _o in KNOWN[:2]:
        _body, ms = _timed_answer(s, r)
        answer_lat.append(ms)
    stats = _stats()

    # M4: hub facts must survive the restart.
    m4_rows = []
    for s, r, o in HUB_FACTS:
        body, ms = _timed_query(s, r)
        m4_rows.append(
            {
                "subject": s,
                "relation": r,
                "expected": o,
                "status": body.get("status"),
                "value": body.get("value"),
                "latency_ms": round(ms, 2),
            }
        )
    m4_ok = sum(
        1
        for row, (_s, _r, expected) in zip(m4_rows, HUB_FACTS)
        if row["status"] == "ACCEPTED" and row["value"] == expected
    )
    m4_rate = round(m4_ok / max(1, len(HUB_FACTS)), 4)

    return {
        "M1_tool_honesty": {
            "rate": m1_rate,
            "honest": m1_honest,
            "total": len(m1_rows),
            "p50_ms": _pct(m1_lat, 0.50),
            "p95_ms": _pct(m1_lat, 0.95),
            "rows": m1_rows,
        },
        "M2_invention_rate": {
            "rate": m2_invention_rate,
            "invented": m2_invented,
            "total": len(m2_rows),
            "rows": m2_rows,
        },
        "M3_latency_capacity": {
            "answer_p50_ms": _pct(answer_lat, 0.50),
            "answer_p95_ms": _pct(answer_lat, 0.95),
            "facts": int(stats.get("facts", 0)),
            "entities": int(stats.get("entities", 0)),
            "core_matrix": stats.get("core_matrix"),
            "latent_rank": stats.get("latent_rank"),
        },
        "M4_hub_durability": {
            "rate": m4_rate,
            "survived": m4_ok,
            "total": len(HUB_FACTS),
            "rows": m4_rows,
        },
        "M5_substrate": _substrate_stats(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--phase",
        choices=("learn", "verify", "both"),
        default="both",
        help="learn corpus, verify after restart, or both in one process",
    )
    args = ap.parse_args()

    if not KEY:
        print("warning: RESILEOS_API_KEY is not set; requests may 401", file=sys.stderr)

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": BASE,
        "phase": args.phase,
    }

    if args.phase in ("learn", "both"):
        report["learn"] = phase_learn()

    if args.phase in ("verify", "both"):
        if args.phase == "both":
            time.sleep(0.5)
        report["verify"] = phase_verify()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items() if k != "verify"}, indent=2))
    if "verify" in report:
        print(json.dumps(report["verify"], indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
