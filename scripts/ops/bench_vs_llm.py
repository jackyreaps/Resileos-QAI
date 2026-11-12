#!/usr/bin/env python3
"""Exact-memory benchmark (Resileos vs an optional LLM baseline).

The Resileos leg needs no API key. It always scores the same 3 known
facts and 12 unknown pairs.

The LLM leg runs only when both BENCH_LLM_URL and BENCH_LLM_KEY are
set, and only on those same pairs. If either variable is missing, the
leg is skipped and its rates stay null. A failed call is not counted
as an invention or a hit. The key and the raw URL are not printed and
are not written into the artifact.

Usage:
    PYTHONPATH=src python scripts/ops/bench_vs_llm.py \
        --out landing/artifacts/report_memory_vs_llm_YYYY-MM-DD.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bench.measure_meta import dated_artifact, environment, redact_text, utc_now
from resileos.ui.attach_scale import attach_scale

# Known facts for exact-match; unknowns for invent-rate.
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


def _shown_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return str(value)


def run_store_bench(learn_fn, query_fn, *, backend: str) -> dict:
    for subject, relation, obj in KNOWN:
        learn_fn(subject, relation, obj)
    hits = 0
    latencies = []
    known_rows = []
    for subject, relation, obj in KNOWN:
        started = time.perf_counter()
        value = query_fn(subject, relation)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        exact = str(value) == obj
        if exact:
            hits += 1
        known_rows.append(
            {
                "subject": subject,
                "relation": relation,
                "expected": obj,
                "got": _shown_value(value),
                "exact": exact,
                "latency_ms": elapsed,
            }
        )
    invent = 0
    unknown_rows = []
    for subject, relation, _obj in UNKNOWN:
        value = query_fn(subject, relation)
        invented = value is not None and value != "" and value != []
        if invented:
            invent += 1
        unknown_rows.append(
            {
                "subject": subject,
                "relation": relation,
                "got": _shown_value(value),
                "invented": invented,
            }
        )
    return {
        "exact_match_rate": hits / len(KNOWN),
        "invent_rate": invent / len(UNKNOWN),
        "abstain_rate": (len(UNKNOWN) - invent) / len(UNKNOWN),
        "n_known": len(KNOWN),
        "n_unknown": len(UNKNOWN),
        "p50_latency_ms_known": median(latencies),
        "mean_latency_ms_known": sum(latencies) / max(len(latencies), 1),
        "backend": backend,
        "known": known_rows,
        "unknown": unknown_rows,
    }


def _endpoint_host(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.username or parts.password or not parts.hostname:
        return None
    return parts.hostname


def _llm_one(url: str, key: str, subject: str, relation: str) -> tuple[str | None, str | None]:
    import urllib.request

    prompt = (
        "Answer with only the object value if known, else say UNKNOWN: "
        f"{subject} {relation}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps({"prompt": prompt}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
        return str(payload.get("text", "")), None
    except Exception as exc:
        return None, type(exc).__name__


def llm_leg() -> dict:
    """Score the same pairs, or skip without inventing rates.

    Both BENCH_LLM_URL and BENCH_LLM_KEY are required. The returned
    dict never contains the key or the raw URL.
    """
    url = os.getenv("BENCH_LLM_URL", "").strip()
    key = os.getenv("BENCH_LLM_KEY", "").strip()
    skipped = {
        "status": "skipped",
        "exact_match_rate": None,
        "invent_rate": None,
        "n_known": len(KNOWN),
        "n_unknown": len(UNKNOWN),
        "url_set": bool(url),
        "key_set": bool(key),
        "pairs": [],
    }
    if not url or not key:
        missing = []
        if not url:
            missing.append("BENCH_LLM_URL")
        if not key:
            missing.append("BENCH_LLM_KEY")
        skipped["reason"] = "LLM leg skipped: " + " and ".join(missing) + " unset"
        return skipped

    host = _endpoint_host(url)
    rows = []
    errors = 0
    known_hits = 0
    invent = 0
    for subject, relation, expected in [*KNOWN, *UNKNOWN]:
        text, error = _llm_one(url, key, subject, relation)
        kind = "known" if expected is not None else "unknown"
        if error:
            errors += 1
            rows.append(
                {
                    "subject": subject,
                    "relation": relation,
                    "kind": kind,
                    "error": error,
                }
            )
            continue
        shown = redact_text(text or "").strip()
        if len(shown) > 200:
            shown = shown[:200]
        if expected is not None:
            exact = shown == expected
            if exact:
                known_hits += 1
            rows.append(
                {
                    "subject": subject,
                    "relation": relation,
                    "kind": kind,
                    "exact": exact,
                    "text": shown,
                }
            )
        else:
            invented = bool(shown) and "UNKNOWN" not in shown.upper()
            if invented:
                invent += 1
            rows.append(
                {
                    "subject": subject,
                    "relation": relation,
                    "kind": kind,
                    "invented": invented,
                    "text": shown,
                }
            )

    report = {
        "status": "incomplete" if errors else "scored",
        "exact_match_rate": None,
        "invent_rate": None,
        "n_known": len(KNOWN),
        "n_unknown": len(UNKNOWN),
        "url_set": True,
        "key_set": True,
        "endpoint_host": host,
        "errors": errors,
        "pairs": rows,
    }
    if errors:
        report["reason"] = (
            "one or more LLM calls failed; rates are null so a failed "
            "call is not counted as an invention or a miss"
        )
        return report
    report["exact_match_rate"] = known_hits / len(KNOWN)
    report["invent_rate"] = invent / len(UNKNOWN)
    report["abstain_rate"] = (len(UNKNOWN) - invent) / len(UNKNOWN)
    report["reason"] = "scored the same 3 known and 12 unknown pairs"
    return report


def build_store():
    """Live Titanos when it imports. Otherwise the in-memory dict stub."""
    store: dict[tuple[str, str], str] = {}
    backend = "dict_stub"
    backend_error = ""

    def learn(subject, relation, obj):
        store[(subject, relation)] = obj

    def query(subject, relation):
        return store.get((subject, relation))

    try:
        from titanos import Titanos, TitanosConfig

        titan = Titanos(TitanosConfig())

        def learn(subject, relation, obj):
            titan.learn(subject, relation, obj)

        def query(subject, relation):
            answer = titan.ask(subject, relation)
            return getattr(answer, "value", answer)

        backend = "titanos"
    except Exception as exc:
        backend_error = type(exc).__name__
        print(f"bench: Titanos unavailable ({backend_error}); using dict stub")

    return learn, query, backend, backend_error


def public_json(report: dict) -> str:
    return redact_text(json.dumps(report, indent=2)) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or dated_artifact("memory_vs_llm")

    learn, query, backend, backend_error = build_store()
    resileos = run_store_bench(learn, query, backend=backend)
    if backend_error:
        resileos["backend_error"] = backend_error
    llm = llm_leg()
    report = {
        "measured_at": utc_now(),
        "environment": environment(),
        "scope": (
            "Exact recall on 3 stored facts and abstention on 12 absent "
            "pairs. This report does not score generation, coding, or "
            "general reasoning."
        ),
        "resileos": resileos,
        "llm_baseline": llm,
    }
    text = public_json(attach_scale(report))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
