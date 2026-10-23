#!/usr/bin/env python3
"""Aggregate multi-seed training probe reports.

Reads N report JSONs written by run_aggregate_training_probe.py (one per
seed) and produces a combined report with mean / std / sign-stability /
significance. The load-bearing number is `improvement_kappa`, and a
single seed is not a result — it is one draw from a noisy distribution
on n=32 facts. This script computes the actual distribution.

Significance rule: `mean / (std / sqrt(n)) > 2.0` and sign-stable across
seeds. With n=3 that is a t-statistic of 2, ~2-sigma. Weaker than a
formal test but honest about the sample size.

Usage:
    python scripts/aggregate_seed_reports.py \
        --reports artifacts/report_aggregate_seed0.json \
                  artifacts/report_aggregate_seed1.json \
                  artifacts/report_aggregate_seed2.json \
        --out artifacts/report_aggregate_multi_seed.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def aggregate(reports: list[dict]) -> dict:
    if len(reports) < 2:
        raise SystemExit(
            f"need at least 2 reports to aggregate; got {len(reports)}"
        )

    improvements = np.array(
        [float(r["improvement_kappa"]) for r in reports]
    )
    baselines = np.array([float(r["baseline_nll"]) for r in reports])
    nlls_on = np.array([float(r["nll_kappa_on"]) for r in reports])
    nlls_off = np.array([float(r["nll_kappa_off"]) for r in reports])

    n = len(improvements)
    mean_kappa = float(improvements.mean())
    std_kappa = float(improvements.std(ddof=1)) if n > 1 else 0.0
    se_kappa = std_kappa / float(np.sqrt(n)) if n > 1 else 0.0

    all_positive = bool((improvements > 0).all())
    all_negative = bool((improvements < 0).all())
    mean_positive = mean_kappa > 0.0
    sign_stable = (all_positive and mean_positive) or (
        all_negative and not mean_positive
    )

    if se_kappa > 0.0:
        t_stat = mean_kappa / se_kappa
    else:
        # All seeds identical: infinite t if nonzero, 0 if zero
        t_stat = float("inf") if abs(mean_kappa) > 1e-12 else 0.0

    significant = bool(sign_stable and t_stat > 2.0)

    if not significant:
        verdict = (
            "not significant across seeds — one draw is not a result"
        )
    elif mean_positive:
        verdict = (
            "coupling reduces object-token NLL (κ=2 < κ=0) — "
            "Path B supported on this task"
        )
    else:
        verdict = (
            "coupling increases object-token NLL (κ=2 > κ=0) — "
            "aggregate features hurt the carrier"
        )

    seeds = [r.get("seed", i) for i, r in enumerate(reports)]
    decoders = {r.get("decoder", "unknown") for r in reports}
    if len(decoders) > 1:
        print(
            f"warning: multiple decoders across seeds: {decoders}",
            file=sys.stderr,
        )

    return {
        "probe": "aggregate_training_multi_seed",
        "n_seeds": int(n),
        "seeds": seeds,
        "decoder": list(decoders)[0] if len(decoders) == 1 else list(decoders),
        "baseline_nll_mean": float(baselines.mean()),
        "baseline_nll_std": (
            float(baselines.std(ddof=1)) if n > 1 else 0.0
        ),
        "nll_kappa_off_mean": float(nlls_off.mean()),
        "nll_kappa_off_std": (
            float(nlls_off.std(ddof=1)) if n > 1 else 0.0
        ),
        "nll_kappa_on_mean": float(nlls_on.mean()),
        "nll_kappa_on_std": (
            float(nlls_on.std(ddof=1)) if n > 1 else 0.0
        ),
        "improvement_kappa_mean": mean_kappa,
        "improvement_kappa_std": std_kappa,
        "improvement_kappa_se": se_kappa,
        "improvement_kappa_t": float(t_stat)
        if t_stat != float("inf")
        else "inf",
        "improvement_kappa_all_positive": all_positive,
        "improvement_kappa_all_negative": all_negative,
        "improvement_kappa_sign_stable": bool(sign_stable),
        "significant": significant,
        "per_seed_improvement_kappa": improvements.tolist(),
        "verdict": verdict,
        "notes": [
            "improvement_kappa = nll_k0 - nll_k2. Positive means coupling helps.",
            "Significance: |mean| / (std/sqrt(n)) > 2 AND all seeds same sign.",
            "With n=3, a t of 2 is ~2-sigma; adjust the threshold for more seeds.",
            "32-fact task has accuracy steps of ~3% per fact; treat accuracy as sanity only.",
            "Carrier scale sanity: check per-seed carrier_on_scale_final in the raw reports.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate multi-seed probe reports")
    ap.add_argument(
        "--reports",
        nargs="+",
        required=True,
        help="paths to per-seed report JSONs",
    )
    ap.add_argument(
        "--out",
        type=str,
        default="artifacts/report_aggregate_multi_seed.json",
    )
    args = ap.parse_args()

    reports = [_load(Path(p)) for p in args.reports]
    combined = aggregate(reports)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(combined, indent=2))

    print(f"n_seeds: {combined['n_seeds']}")
    print(f"seeds:   {combined['seeds']}")
    print(f"decoder: {combined['decoder']}")
    print()
    print(
        f"baseline NLL:     {combined['baseline_nll_mean']:.4f} "
        f"± {combined['baseline_nll_std']:.4f}"
    )
    print(
        f"κ=0 carrier NLL:  {combined['nll_kappa_off_mean']:.4f} "
        f"± {combined['nll_kappa_off_std']:.4f}"
    )
    print(
        f"κ=2 carrier NLL:  {combined['nll_kappa_on_mean']:.4f} "
        f"± {combined['nll_kappa_on_std']:.4f}"
    )
    print()
    print(
        f"improvement_kappa: mean={combined['improvement_kappa_mean']:+.4f}  "
        f"std={combined['improvement_kappa_std']:.4f}  "
        f"t={combined['improvement_kappa_t']}"
    )
    print(
        f"sign_stable: {combined['improvement_kappa_sign_stable']}  "
        f"significant: {combined['significant']}"
    )
    print(
        f"per-seed: "
        f"{[f'{x:+.4f}' for x in combined['per_seed_improvement_kappa']]}"
    )
    print()
    print(f"verdict: {combined['verdict']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
