#!/usr/bin/env python3
"""M5: 100-query latency for exact ``ask`` and exact ``chain``.

In-process calls on a fresh ``Titanos(TitanosConfig())`` seeded with
``configs/titanos-facts.json``. One untimed warmup call per operation
is excluded. The 100 timed calls then cycle the exact catalog.

An exact ask is a ``(subject, relation)`` with one stored object.
An exact chain is two hops that are each single-valued, so the
expected final object is unique.

This does not open an HTTP server and does not change the store code.

Usage:
    PYTHONPATH=src:scripts python scripts/bench/latency_m5.py \
        --out landing/artifacts/report_latency_m5_YYYY-MM-DD.json
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from bench.measure_meta import dated_artifact, environment, latency_summary, utc_now

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FACTS = ROOT / "configs" / "titanos-facts.json"
N_QUERIES = 100


def load_facts(path: Path) -> list[tuple[str, str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts = []
    for row in raw.get("facts", []):
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            facts.append((str(row[0]), str(row[1]), str(row[2])))
    return facts


def single_valued(facts: list[tuple[str, str, str]]) -> dict[tuple[str, str], str]:
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for subject, relation, obj in facts:
        grouped[(subject, relation)].add(obj)
    exact: dict[tuple[str, str], str] = {}
    for key, objs in grouped.items():
        if len(objs) == 1:
            exact[key] = next(iter(objs))
    return exact


def exact_asks(facts: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    rows = [
        (subject, relation, obj)
        for (subject, relation), obj in single_valued(facts).items()
    ]
    rows.sort()
    return rows


def exact_chains(
    facts: list[tuple[str, str, str]],
) -> list[tuple[str, list[str], str]]:
    exact = single_valued(facts)
    by_subject: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for (subject, relation), obj in exact.items():
        by_subject[subject].append((relation, obj))
    chains = []
    for (subject, relation), mid in exact.items():
        for relation2, final in by_subject.get(mid, []):
            chains.append((subject, [relation, relation2], final))
    chains.sort(key=lambda item: (item[0], item[1][0], item[1][1], item[2]))
    return chains


def _cycle(catalog: list, n: int) -> list:
    if not catalog:
        return []
    return [catalog[i % len(catalog)] for i in range(n)]


def measure(facts_path: Path = DEFAULT_FACTS, n: int = N_QUERIES) -> dict:
    from titanos import Titanos, TitanosConfig

    facts = load_facts(facts_path)
    asks = exact_asks(facts)
    chains = exact_chains(facts)
    titan = Titanos(TitanosConfig())
    for subject, relation, obj in facts:
        titan.learn(subject, relation, obj)

    report: dict = {
        "probe": "latency_m5",
        "metric": "M5",
        "measured_at": utc_now(),
        "environment": environment(),
        "transport": "in-process Titanos.ask and Titanos.chain",
        "http": {
            "status": "skipped",
            "reason": (
                "No API server was started. Latency is the method call "
                "on this VM, not a socket round trip."
            ),
        },
        "corpus": str(facts_path.relative_to(ROOT)) if facts_path.is_absolute() else str(facts_path),
        "n_facts_seeded": len(facts),
        "config": "Titanos(TitanosConfig())",
        "n_queries": n,
        "warmup_calls_excluded": 1,
        "target_p95_ms": 500,
    }

    if not asks:
        report["ask"] = {"status": "skipped", "reason": "no single-valued facts"}
    else:
        planned = _cycle(asks, n)
        titan.ask(planned[0][0], planned[0][1])

        def _run_ask(index: int):
            subject, relation, expected = planned[index]
            answer = titan.ask(subject, relation)
            return answer, expected

        ask_results = []
        samples = []
        exact_samples = []
        for index in range(n):
            started = time.perf_counter()
            answer, expected = _run_ask(index)
            elapsed = (time.perf_counter() - started) * 1000.0
            samples.append(elapsed)
            exact = answer.status == "ACCEPTED" and answer.value == expected
            if exact:
                exact_samples.append(elapsed)
            ask_results.append(exact)
        summary = latency_summary(samples)
        summary["exact_accepts"] = sum(ask_results)
        summary["exact_rate"] = summary["exact_accepts"] / n
        summary["distinct_queries"] = len(asks)
        summary["p50_ms_exact_only"] = latency_summary(exact_samples)["p50_ms"]
        summary["p95_ms_exact_only"] = latency_summary(exact_samples)["p95_ms"]
        summary["p95_under_500ms"] = (
            summary["p95_ms"] is not None and summary["p95_ms"] < 500
        )
        report["ask"] = summary

    if not chains:
        report["chain"] = {
            "status": "skipped",
            "reason": "no two-hop path with a single object on each hop",
        }
    else:
        planned_chains = _cycle(chains, n)
        first = planned_chains[0]
        titan.chain(first[0], first[1])

        samples = []
        exact_samples = []
        exact_hits = 0
        for start, relations, expected in planned_chains:
            started = time.perf_counter()
            answer = titan.chain(start, relations)
            elapsed = (time.perf_counter() - started) * 1000.0
            samples.append(elapsed)
            exact = answer.status == "ACCEPTED" and answer.value == expected
            if exact:
                exact_hits += 1
                exact_samples.append(elapsed)
        summary = latency_summary(samples)
        summary["exact_accepts"] = exact_hits
        summary["exact_rate"] = exact_hits / n
        summary["distinct_queries"] = len(chains)
        summary["p50_ms_exact_only"] = latency_summary(exact_samples)["p50_ms"]
        summary["p95_ms_exact_only"] = latency_summary(exact_samples)["p95_ms"]
        summary["p95_under_500ms"] = (
            summary["p95_ms"] is not None and summary["p95_ms"] < 500
        )
        report["chain"] = summary

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="M5 exact ask/chain latency")
    parser.add_argument("--facts", type=Path, default=DEFAULT_FACTS)
    parser.add_argument("--n", type=int, default=N_QUERIES)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = measure(args.facts, args.n)
    out = args.out or dated_artifact("latency_m5")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    public = {
        "measured_at": report["measured_at"],
        "ask": report.get("ask"),
        "chain": report.get("chain"),
        "out": str(out),
    }
    print(json.dumps(public, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
