#!/usr/bin/env python3
"""RES-304 triad experiment.

Scaling check: MaxCut at n = 10, 20, 30; K random inits per n.
Measures basin volume, depth, boundary dimension, hopping rate, boundary
codimension, and basin entropy. Classifies each condition as constraint,
saturated-boundary, wall, or sheath.

Writes docs/300-substrate/triad-results.md and artifacts/triad_result.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.basin import BasinConfig, measure_basin, basin_entropy
from resileos.substrate.maxcut import (
    random_maxcut,
    random_partition,
    local_search,
    simulated_annealing,
)
from resileos.substrate.sheath import SheathConfig, sheath_metrics


def _hash_partition(p: np.ndarray) -> int:
    bits = (p > 0).astype(int)
    return int(sum(b << i for i, b in enumerate(bits)))


def _run_method(inst, method: str, init: np.ndarray, seed: int) -> np.ndarray:
    if method == "random":
        return init
    if method == "local":
        return local_search(inst, init)
    if method == "anneal":
        return simulated_annealing(inst, init, seed=seed)
    raise ValueError(method)


def best_mode_id(inst, method: str, seed: int, tries: int = 50) -> int:
    """Run the method from `tries` random inits, return hash of best partition."""
    rng = np.random.default_rng(seed)
    best_val, best_id = -1, 0
    for _ in range(tries):
        init = random_partition(inst.n, rng)
        final = _run_method(inst, method, init, seed)
        val = inst.cut_value(final)
        if val > best_val:
            best_val, best_id = val, _hash_partition(final)
    return best_id


def make_step_fn(inst, method: str, seed: int):
    def step_fn(x: np.ndarray) -> int:
        init = np.sign(x)
        init[init == 0] = 1.0
        final = _run_method(inst, method, init, seed)
        return _hash_partition(final)
    return step_fn


def run_condition(n: int, method: str, cfg: BasinConfig, sheath_cfg: SheathConfig):
    inst = random_maxcut(n, edge_prob=0.5, seed=n)
    target = best_mode_id(inst, method, seed=cfg.seed)
    step_fn = make_step_fn(inst, method, seed=cfg.seed)
    m = sheath_metrics(step_fn, target, cfg, sheath_cfg)
    m["method"] = method
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-list", default="10,20,30")
    ap.add_argument("--K", type=int, default=200)
    ap.add_argument("--methods", default="random,local,anneal")
    ap.add_argument("--out-json", type=Path,
                    default=Path("artifacts/triad_result.json"))
    ap.add_argument("--out-md", type=Path,
                    default=Path("docs/300-substrate/triad-results.md"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    ns = [int(x) for x in args.n_list.split(",")]
    methods = [m.strip() for m in args.methods.split(",")]
    cfg = BasinConfig(n_states=args.K, seed=args.seed)
    sheath_cfg = SheathConfig()

    results = []
    for n in ns:
        cfg.n_dims = n
        for method in methods:
            row = run_condition(n, method, cfg, sheath_cfg)
            results.append(row)
            print(
                f"[n={n:>3} {method:>6}] vol={row['volume']:.4f} "
                f"depth={row['depth']:.4f} bdim={row['boundary_dim']:.3f} "
                f"codim={row['boundary_codim']:.3f} "
                f"entropy={row['basin_entropy']:.2f} "
                f"regime={row['regime']}"
            )

    fits = {}
    print()
    for method in methods:
        pts = [(r["n"], r["volume"]) for r in results
               if r["method"] == method and r["volume"] > 0]
        if len(pts) >= 2:
            slope, intercept = np.polyfit(
                np.log([p[0] for p in pts]),
                np.log([p[1] for p in pts]),
                1,
            )
            fits[method] = {"slope": float(slope), "intercept": float(intercept)}
            print(f"[fit {method}] volume ~ n^({slope:.3f})")

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({
        "config": {"K": args.K, "n_list": ns, "methods": methods,
                   "seed": args.seed},
        "results": results,
        "fits": fits,
    }, indent=2))

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RES-304 Triad Results",
        "",
        f"K = {args.K} inits per condition. MaxCut, edge probability 0.5.",
        "",
        "## Basin metrics",
        "",
        "| n | method | volume | depth | bdim | codim | entropy | regime |",
        "|---|--------|--------|-------|------|-------|---------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r['n']} | {r['method']} | {r['volume']:.4f} | "
            f"{r['depth']:.4f} | {r['boundary_dim']:.3f} | "
            f"{r['boundary_codim']:.3f} | {r['basin_entropy']:.2f} | "
            f"{r['regime']} |"
        )
    lines += ["", "## Scaling fits (volume ~ n^slope)", ""]
    lines += ["| method | slope | intercept |", "|--------|-------|-----------|"]
    for m, f in fits.items():
        lines.append(f"| {m} | {f['slope']:.3f} | {f['intercept']:.3f} |")
    lines.append("")
    args.out_md.write_text("\n".join(lines))

    print(f"\n[write] {args.out_json}")
    print(f"[write] {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
