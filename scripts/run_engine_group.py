#!/usr/bin/env python3
"""Smoke-run multi-engine composition (RES-318).

Steps an EngineGroup and prints CoupledPacket summaries. This is the
substrate path the quantum-capable stack needs before any training gate:
correlated multi-stream state, not single-core synthetic packets.

Usage:
    PYTHONPATH=src python scripts/run_engine_group.py
    PYTHONPATH=src python scripts/run_engine_group.py --n 5 --steps 20
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from resileos.core import CoreConfig
from resileos.substrate.coupling import CouplingField
from resileos.substrate.engine_group import EngineGroup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--m", type=int, default=8)
    ap.add_argument("--r", type=int, default=4)
    ap.add_argument("--kappa", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    configs = [CoreConfig(m=args.m, n=args.m, r=args.r) for _ in range(args.n)]
    field = CouplingField(
        n_engines=args.n, kappa=args.kappa, seed=args.seed,
    )
    group = EngineGroup(configs, field, seed=args.seed)
    rng = np.random.default_rng(args.seed)

    rows = []
    for t in range(args.steps):
        W = [rng.standard_normal((args.m, args.m)) for _ in range(args.n)]
        drives = rng.standard_normal(args.n) * 0.1
        cp = group.step(W, drives=drives)
        row = {
            "t": t,
            "R_shared": float(cp.R_shared),
            "phases": [float(x) for x in cp.phases],
            "F_res": [float(p.F_res) for p in cp.packets],
            "DeltaS": [float(p.DeltaS) for p in cp.packets],
            "mu": [float(p.mu) for p in cp.packets],
        }
        rows.append(row)
        print(
            f"t={t:3d}  R={cp.R_shared:.4f}  "
            f"F_res={[round(x, 4) for x in row['F_res']]}"
        )

    R = np.array([r["R_shared"] for r in rows])
    summary = {
        "n_engines": args.n,
        "steps": args.steps,
        "kappa": args.kappa,
        "R_mean": float(R.mean()),
        "R_std": float(R.std()),
        "trace": rows,
        "note": (
            "Multi-engine CoupledPacket stream. Use this class of data "
            "for any framework-native training question; single-engine "
            "synthetic packets are diagnostics only."
        ),
    }
    out = Path(args.out) if args.out else Path("artifacts/report_engine_group.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
