#!/usr/bin/env python3
"""Temporal conflict probe (RES-332 §7 item 5 / M9).

Measures temporal conflict rate on the 120-fact corpus after the
valid-time extension. A "temporal conflict" is two chronos-valid facts
for the same (subject, relation) at a given as_of moment.

    M9_target: 0.0 at the corpus's declared as_of (no conflicts on the
    reference facts, because the reference set is single-valued per
    (s, r) at any moment).

    M9 on synthetic overlap: > 0.0 by construction (the probe inserts
    conflicting facts with overlapping validity and verifies they
    surface as CONFLICT, not silently overwrite).

Usage:
    PYTHONPATH=src python scripts/run_temporal_probe.py \
        --facts configs/titanos-facts.json \
        --out artifacts/report_temporal_probe.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# Relations that may hold several objects at once. A temporal conflict
# is two different objects on a single-valued relation whose windows
# both cover the same as_of.
_MULTI_VALUED = {"parent_of", "sibling_of", "spouse_of", "symbol_of"}


def _windows_overlap(facts_for_pair) -> bool:
    """True when two explicit or unbounded windows cover a shared moment.

    The caller already filtered to rows valid at one as_of, so any two
    of those rows overlap at that moment.
    """
    return len(facts_for_pair) > 1


def _reference_corpus_m9(titan, facts, as_of_list):
    """M9 counts single-valued relations with more than one object.

    parent_of and the other multi-valued relations are not conflicts.
    """
    conflicts = 0
    checks = 0
    seen = set()
    for as_of in as_of_list:
        for s, r, _o in facts:
            if r in _MULTI_VALUED:
                continue
            key = (as_of, s, r)
            if key in seen:
                continue
            seen.add(key)
            rows = titan.ask_list(s, r, as_of=as_of)
            checks += 1
            if len(rows) > 1 and _windows_overlap(rows):
                conflicts += 1
    return {
        "checks": checks,
        "conflicts": conflicts,
        "M9": conflicts / checks if checks else 0.0,
        "target": 0.0,
        "pass": conflicts == 0,
    }


def _synthetic_overlap_m9(titan, as_of_list):
    """M9 on synthetic overlap: insert two facts for the same (s, r)
    with overlapping validity. The store must return both, not overwrite.
    """
    s, r = "test:temporal_subject", "capital_of"
    titan.learn(s, r, "obj_A",
                valid_from="1800-01-01", valid_to="1900-01-01")
    titan.learn(s, r, "obj_B",
                valid_from="1850-01-01", valid_to=None)

    conflicts = 0
    checks = 0
    overlap_as_ofs = ["1860-01-01", "1880-01-01"]
    for as_of in overlap_as_ofs:
        rows = titan.ask_list(s, r, as_of=as_of)
        checks += 1
        if len(rows) > 1:
            conflicts += 1

    # Before B starts only A is valid. After A ends only B is valid.
    # 1750 is before both windows, so it is not a single-valued moment.
    non_overlap = ["1820-01-01", "1950-01-01"]
    for as_of in non_overlap:
        rows = titan.ask_list(s, r, as_of=as_of)
        checks += 1
        if len(rows) != 1:
            conflicts += 1

    return {
        "checks": checks,
        "conflicts_in_overlap": 2,
        "conflicts_detected": sum(
            1 for a in overlap_as_ofs
            if len(titan.ask_list(s, r, as_of=a)) > 1
        ),
        "non_overlap_singular": sum(
            1 for a in non_overlap
            if len(titan.ask_list(s, r, as_of=a)) == 1
        ),
        "pass": (
            sum(1 for a in overlap_as_ofs
                if len(titan.ask_list(s, r, as_of=a)) > 1) == 2
            and sum(1 for a in non_overlap
                    if len(titan.ask_list(s, r, as_of=a)) == 1) == 2
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Temporal conflict probe (M9)")
    ap.add_argument("--facts", default="configs/titanos-facts.json")
    ap.add_argument(
        "--out", default="artifacts/report_temporal_probe.json"
    )
    args = ap.parse_args()

    # Import here so a missing temporal extension fails at the right point
    try:
        from titanos import Titanos, TitanosConfig
    except ImportError as e:
        raise SystemExit(f"titanos not importable: {e}")

    facts_path = Path(args.facts)
    if not facts_path.exists():
        raise SystemExit(f"facts not found: {facts_path}")

    raw = json.loads(facts_path.read_text(encoding="utf-8"))
    facts = [
        tuple(row) for row in raw.get("facts", [])
        if isinstance(row, (list, tuple)) and len(row) == 3
    ]
    if not facts:
        raise SystemExit("no facts loaded")

    titan = Titanos(TitanosConfig(
        dim=10000, m=100, n=100, r=8, n_loops=12, seed=1337,
    ))

    # Seed with validity = (None, None) for all reference facts
    for s, r, o in facts:
        try:
            titan.learn(s, r, o, valid_from=None, valid_to=None)
        except TypeError:
            raise SystemExit(
                "learn() does not accept valid_from/valid_to. "
                "Temporal extension not yet applied."
            )

    as_of_list = [
        "1900-01-01", "2000-01-01", "2026-11-09",
    ]
    ref = _reference_corpus_m9(titan, facts, as_of_list)
    synth = _synthetic_overlap_m9(titan, as_of_list)

    report = {
        "probe": "temporal_conflict",
        "metric": "M9",
        "corpus": str(facts_path),
        "n_facts": len(facts),
        "reference": ref,
        "synthetic_overlap": synth,
        "pass": bool(ref["pass"] and synth["pass"]),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print(f"reference M9:    {ref['M9']:.4f}  ({ref['conflicts']}/{ref['checks']})  "
          f"{'PASS' if ref['pass'] else 'FAIL'}")
    print(f"synthetic M9:    overlap_detected={synth['conflicts_detected']}/2  "
          f"non_overlap_singular={synth['non_overlap_singular']}/2  "
          f"{'PASS' if synth['pass'] else 'FAIL'}")
    print(f"wrote {out}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
