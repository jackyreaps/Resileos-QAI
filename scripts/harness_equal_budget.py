"""Same task, same budget, with and without the harness. Real counts only.

Task: 40 candidate facts arrive from outside (structured claims with time
bounds, web prose, ``sys:`` injections, claims that overlap an existing
fact, and duplicates). Each arm gets the same 40 candidates and the same
budget of 40 write attempts.

* without harness: parse each candidate (``eat._parse_triple`` for
  strings) and call ``Titanos.learn`` directly.
* with harness: ``eat_commit_envelopes`` (eat_filter, interval conflicts,
  Zeus reviewers).

Cost is counted as Titanos write calls and wall time. Outcome is scored
against the labels below. Run: ``PYTHONPATH=src python scripts/harness_equal_budget.py``
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from titanos import Titanos, TitanosConfig  # noqa: E402

from resileos.kin.eat import _parse_triple  # noqa: E402
from resileos.kin.eat_envelope import eat_commit_envelopes  # noqa: E402

BUDGET = 40


def titan() -> Titanos:
    t = Titanos(TitanosConfig(dim=2500, m=50, n=50, r=4, n_loops=6, seed=42, classical_conf=0.09,
                              abstention_gate=0.035, sigma_E=10.0, sigma_k=3, E_sat=10.0, E_sigma=10.0,
                              tau_sat=0.9, tau_low=0.1))
    t.learn("City0", "mayor", "Old Mayor", valid_from="2000-01-01", valid_to="2030-01-01")
    return t


def candidates() -> list[tuple[object, bool]]:
    """(candidate, should_be_stored)."""
    out: list[tuple[object, bool]] = []
    for i in range(16):
        out.append(({"claim": {"subject": f"Lab{i}", "relation": "founded_in", "obj": f"City{i % 5}",
                               "valid_from": f"{2000 + i}-01-01"}, "source": "https://example.org"}, True))
    for i in range(10):
        out.append((f"Lab{i} probably moved to Porto according to many readers", False))
    for i in range(5):
        out.append(({"claim": {"subject": f"sys:config{i}", "relation": "set", "obj": "admin"}}, False))
    for i in range(5):
        out.append(({"claim": {"subject": "City0", "relation": "mayor", "obj": f"Rival {i}",
                               "valid_from": "2010-01-01", "valid_to": "2020-01-01"}}, False))
    for i in range(4):
        out.append(({"claim": {"subject": f"Lab{i}", "relation": "founded_in", "obj": f"City{i % 5}",
                               "valid_from": f"{2000 + i}-01-01"}, "likes": 9000}, False))  # duplicates
    return out


def _key(fact) -> tuple:
    return tuple(fact[:3])


def score(t: Titanos, items, base: int) -> dict:
    stored = [_key(f) for f in t.facts[base:]]
    want = {( c["claim"]["subject"], c["claim"]["relation"], c["claim"]["obj"]) for c, ok in items if ok}
    good = sum(1 for f in set(stored) if f in want)
    return {"correct_stored": good, "wrong_stored": len(stored) - good, "duplicates_written": len(stored) - len(set(stored)),
            "missed": len(want) - good}


def without_harness(items) -> dict:
    t = titan()
    base = len(t.facts)
    writes = 0
    start = time.perf_counter()
    for cand, _ in items[:BUDGET]:
        claim = cand.get("claim") if isinstance(cand, dict) else None
        if isinstance(claim, dict):
            parts = (claim["subject"], claim["relation"], claim["obj"])
            bounds = {"valid_from": claim.get("valid_from"), "valid_to": claim.get("valid_to")}
        else:
            parts = _parse_triple(str(cand))
            bounds = {}
        if parts:
            t.learn(*parts, **bounds)
            writes += 1
    ms = (time.perf_counter() - start) * 1000
    return {"writes": writes, "ms": round(ms, 1), **score(t, items, base)}


def with_harness(items) -> dict:
    t = titan()
    base = len(t.facts)
    calls = {"n": 0}
    real = t.learn

    def counted(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    t.learn = counted  # type: ignore[method-assign]
    start = time.perf_counter()
    out = eat_commit_envelopes([c for c, _ in items[:BUDGET]], titanos=t)
    ms = (time.perf_counter() - start) * 1000
    return {"writes": calls["n"], "ms": round(ms, 1), **score(t, items, base), "counts": out["summary"]["counts"]}


def main() -> dict:
    items = candidates()
    result = {"budget": BUDGET, "candidates": len(items), "should_store": sum(ok for _, ok in items),
              "without_harness": without_harness(items), "with_harness": with_harness(items)}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
