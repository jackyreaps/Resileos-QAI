#!/usr/bin/env python3
"""CHSH scan over the Kuramoto field regimes (substrate entanglement probe).

Drives the KuramotoField to EXPLORING, MIXED, and LOCKED coupling, then
reports for each:
    - mean order parameter R
    - CHSH value S (classical bound 2; Tsirelson bound 2*sqrt(2))
    - the four correlators E(a_i, b_j)
    - mutual information between partitioned subsystems

Interpretation rule (per the substrate documentation):
    LOCKED CHSH > 2   -> substrate correlations look quantum-like under
                         this coarse-graining.
    all regimes <= 2  -> classical phase field; any quantum reading is
                         external interpretation, not an emergent
                         property.

Usage:
    python scripts/run_chsh_scan.py --r 8 --n-samples 2000 --seed 0 \\
        --out artifacts/chsh_scan.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.entanglement import scan_regimes  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=int, default=8)
    ap.add_argument("--n-samples", type=int, default=2000)
    ap.add_argument("--warmup", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scheme", default="half",
                    choices=["half", "even_odd", "random"])
    ap.add_argument("--out", type=Path,
                    default=Path("artifacts/chsh_scan.json"))
    args = ap.parse_args()

    print(f"[chsh] r={args.r} n_samples={args.n_samples} "
          f"warmup={args.warmup} scheme={args.scheme} seed={args.seed}")
    results = scan_regimes(
        r=args.r, n_samples=args.n_samples, warmup=args.warmup,
        seed=args.seed, scheme=args.scheme,
    )

    print()
    print(f"{'regime':<12} {'kappa':>6} {'R_mean':>8} {'R_std':>8} "
          f"{'CHSH':>8} {'MI':>8}  verdict")
    print("-" * 72)
    any_violates = False
    for regime, r in results.items():
        verdict = "QUANTUM-LIKE" if r["violates_classical"] else "classical"
        print(f"{regime:<12} {r['kappa']:>6.2f} {r['R_mean']:>8.4f} "
              f"{r['R_std']:>8.4f} {r['CHSH']:>8.4f} "
              f"{r['MI']:>8.4f}  {verdict}")
        any_violates = any_violates or r["violates_classical"]

    print()
    if any_violates:
        print("[verdict] At least one regime exceeds the classical "
              "CHSH bound.")
        print("          This is evidence for the emergence reading "
              "under the given")
        print("          coarse-graining and settings.")
    else:
        print("[verdict] All regimes within the classical CHSH bound "
              "(|S| <= 2).")
        print("          Consistent with a classical phase field. Any "
              "'quantum'")
        print("          behaviour attributed to the substrate must be "
              "supplied")
        print("          by the consumer, not emergent from the field.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "config": {
            "r": args.r, "n_samples": args.n_samples,
            "warmup": args.warmup, "seed": args.seed,
            "scheme": args.scheme,
        },
        "results": results,
        "any_violation": any_violates,
    }, indent=2))
    print(f"\n[write] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
