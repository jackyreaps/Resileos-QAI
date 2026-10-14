#!/usr/bin/env python3
"""Sheath onset vs size.

Sweeps n across the triad sizes and beyond, measuring boundary codimension
and depth at each size. Reports the n at which the landscape flips from
constraint to sheath.

Writes artifacts/sheath_scale.json and docs/300-substrate/sheath-results.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.basin import BasinConfig
from resileos.substrate.sheath import SheathConfig, sheath_metrics
from resileos.substrate.maxcut import random_maxcut
from scripts.run_triad import make_step_fn, best_mode_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-list", default="10,15,20,25,30,40,50")
    ap.add_argument("--K", type=int, default=200)
    ap.add_argument("--method", default="local")
    ap.add_argument("--out-json", type=Path,
                    default=Path("artifacts/sheath_scale.json"))
    ap.add_argument("--out-md", type=Path,
                    default=Path("docs/300-substrate/sheath-results.md"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    ns = [int(x) for x in args.n_list.split(",")]
    cfg = BasinConfig(n_states=args.K, seed=args.seed)
    sheath_cfg = SheathConfig()

    rows = []
    for n in ns:
        cfg.n_dims = n
        inst = random_maxcut(n, edge_prob=0.5, seed=n)
        target = best_mode_id(inst, args.method, seed=cfg.seed)
        step_fn = make_step_fn(inst, args.method, seed=cfg.seed)
        m = sheath_metrics(step_fn, target, cfg, sheath_cfg)
        rows.append(m)
        print(
            f"[n={n:>3}] vol={m['volume']:.4f} depth={m['depth']:.4f} "
            f"bdim={m['boundary_dim']:.3f} codim={m['boundary_codim']:.3f} "
            f"entropy={m['basin_entropy']:.2f} regime={m['regime']}"
        )

    # sheath onset: first n where regime == "sheath"
    onset = next((r["n"] for r in rows if r["is_sheath"]), None)
    print(f"\n[onset] sheath first observed at n = {onset}")

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({
        "method": args.method,
        "K": args.K,
        "rows": rows,
        "sheath_onset_n": onset,
    }, indent=2))

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Sheath Onset vs Size",
        "",
        f"Method: {args.method}. K = {args.K}. MaxCut, p = 0.5.",
        f"Sheath first observed at n = {onset}.",
        "",
        "| n | volume | depth | bdim | codim | entropy | regime |",
        "|---|--------|-------|------|-------|---------|--------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['n']} | {r['volume']:.4f} | {r['depth']:.4f} | "
            f"{r['boundary_dim']:.3f} | {r['boundary_codim']:.3f} | "
            f"{r['basin_entropy']:.2f} | {r['regime']} |"
        )
    lines.append("")
    args.out_md.write_text("\n".join(lines))

    print(f"\n[write] {args.out_json}")
    print(f"[write] {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
