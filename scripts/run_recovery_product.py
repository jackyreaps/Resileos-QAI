#!/usr/bin/env python3
"""Run F2 recovery product measurement → artifacts/report_recovery_product.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.recovery import measure_recovery_product


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=int, default=8)
    ap.add_argument("--kappa", type=float, default=2.0)
    ap.add_argument("--n-trials", type=int, default=30)
    ap.add_argument("--perturb-scale", type=float, default=0.8)
    ap.add_argument("--max-steps", type=int, default=400)
    ap.add_argument("--r-min", type=float, default=0.85)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--out",
        type=str,
        default="artifacts/report_recovery_product.json",
    )
    args = ap.parse_args()
    report = measure_recovery_product(
        r=args.r,
        kappa=args.kappa,
        n_trials=args.n_trials,
        perturb_scale=args.perturb_scale,
        max_steps=args.max_steps,
        seed=args.seed,
        r_min=args.r_min,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"recovery_rate: {report['recovery_rate']:.2f}")
    print(f"median_steps:  {report['median_steps']}")
    print(f"mean_steps:    {report['mean_steps']}")
    print(f"R_burnin:      {report['R_after_burnin']:.4f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
