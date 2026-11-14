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

``held_out(params)`` is the held-out coherence suite for the leveled
harness: the same 40 Eat candidates plus 24 labelled routing cases. It is
never used to tune anything; it only scores. It returns the L0/L1
coherence metrics (``upgrade_report.COHERENCE_METRICS``) so an L2 change
(for example a routing threshold in ``metric_thresholds``) can be checked
with ``upgrade_report.guard_l2`` and auto-reverted if it makes any worse.
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


# Routing cases: (probability the residual answer is right, it is right).
# Fixed and labelled by hand; a few confident-but-wrong and unsure-but-right
# cases so a threshold change has something to get wrong.
ROUTE_CASES: list[tuple[float, bool]] = [
    (0.99, True), (0.97, True), (0.95, True), (0.93, True), (0.91, True), (0.88, True),
    (0.86, True), (0.84, False), (0.81, True), (0.79, True), (0.76, True), (0.74, False),
    (0.72, True), (0.69, False), (0.66, False), (0.63, True), (0.6, False), (0.55, False),
    (0.5, False), (0.42, False), (0.35, False), (0.28, False), (0.15, False), (0.05, False),
]


def held_out(params: dict | None = None) -> dict:
    """Score the harness on the held-out suite. Real counts only.

    ``params`` is the L2 operational state (``OperationalStore.state``);
    ``metric_thresholds`` may hold ``route_high`` and ``route_mid``.

    - residual_consistency: share of writes that are neither wrong nor duplicate.
    - verification_rate: share of answered routing cases that were right.
    - correct_abstention: share of should-not cases (Eat negatives and wrong
      routing cases) that were held back.
    - budget_efficiency: right outcomes (correct writes plus correct
      hold-backs) per unit of the 40-attempt budget.
    """
    from resileos.harness.tools import confidence_route

    thresholds = dict((params or {}).get("metric_thresholds") or {})
    high = float(thresholds.get("route_high", 0.99))
    mid = float(thresholds.get("route_mid", 0.7))
    items = candidates()
    eat = with_harness(items)
    negatives = [c for c, ok in items[:BUDGET] if not ok]
    held_back = len(negatives) - eat["wrong_stored"] - eat["duplicates_written"]
    answered = right_answered = wrong = wrong_held = 0
    for p, right in ROUTE_CASES:
        route = confidence_route({"probability": p}, high=high, mid=mid)["route"]
        if route != "escalate_or_abstain":
            answered += 1
            right_answered += int(right)
        if not right:
            wrong += 1
            wrong_held += int(route == "escalate_or_abstain")
    writes = max(1, eat["writes"])
    return {
        "suite": f"held-out: {BUDGET} Eat candidates + {len(ROUTE_CASES)} routing cases",
        "params": {"route_high": high, "route_mid": mid},
        "residual_consistency": round(1 - (eat["wrong_stored"] + eat["duplicates_written"]) / writes, 4),
        "verification_rate": round(right_answered / answered, 4) if answered else 0.0,
        "correct_abstention": round((held_back + wrong_held) / (len(negatives) + wrong), 4),
        "budget_efficiency": round((eat["correct_stored"] + held_back) / BUDGET, 4),
        "counts": {"writes": eat["writes"], "correct_stored": eat["correct_stored"], "answered": answered,
                   "right_answered": right_answered, "wrong_cases": wrong, "wrong_held_back": wrong_held,
                   "eat_negatives": len(negatives), "eat_held_back": held_back},
    }


def main() -> dict:
    items = candidates()
    result = {"budget": BUDGET, "candidates": len(items), "should_store": sum(ok for _, ok in items),
              "without_harness": without_harness(items), "with_harness": with_harness(items),
              "held_out": held_out()}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
