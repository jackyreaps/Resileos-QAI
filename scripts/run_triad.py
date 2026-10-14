#!/usr/bin/env python3
"""RES-304 triad experiment.

Scaling check: MaxCut at n = 10, 20, 30; K = 200 random initializations per n.
Measure basin volume (and optionally depth / hopping) for:
  - random search
  - local search
  - simulated annealing

Optionally apply rank contraction to the comparison and re-measure.

Writes:
  docs/300-substrate/triad-results.md
  artifacts/triad_result.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.basin import BasinConfig, measure_basin  # noqa: E402
from resileos.substrate.maxcut import (  # noqa: E402
    random_maxcut,
    random_partition,
    local_search,
    simulated_annealing,
)


def make_step_fn(inst, method: str, seed: int):
    """Return step_fn: partition_init -> terminal_mode_index.

    The terminal mode is the basin the trajectory lands in: we hash the final
    partition to an integer label so basin_volume can count distinct modes.
    """
    def step_fn(x: np.ndarray) -> int:
        init = np.sign(x)
        init[init == 0] = 1.0
        if method == "random":
            final = init
        elif method == "local":
            final = local_search(inst, init)
        elif method == "anneal":
            final = simulated_annealing(inst, init, seed=seed)
        else:
            raise ValueError(method)
        # hash final partition to a stable mode id
        bits = (final > 0).astype(int)
        return int(sum(b << i for i, b in enumerate(bits)))

    return step_fn


def run_condition(n: int, method: str, target_mode: int, cfg: BasinConfig):
    inst = random_maxcut(n, edge_prob=0.5, seed=n)
    step_fn = make_step_fn(inst, method, seed=cfg.seed)
    res = measure_basin(step_fn, target_mode, cfg)
    return {
        "n": n,
        "method": method,
        "volume": res.volume,
        "depth": res.depth,
        "boundary_dim": res.boundary_dim,
        "hopping_rate": res.hopping_rate,
        "mode_counts": res.mode_counts,
    }


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
    results = []
    for n in ns:
        cfg.n_dims = n
        for method in methods:
            # target mode = 0 is arbitrary; volume is measured against whichever
            # mode dominates, so use 0 and interpret volume as "landed in mode 0"
            # to keep target consistent across conditions.
            row = run_condition(n, method, target_mode=0, cfg=cfg)
            results.append(row)
            print(f"[n={n:>3} {method:>6}] vol={row['volume']:.4f} "
                  f"depth={row['depth']:.4f} bdim={row['boundary_dim']:.3f} "
                  f"hop={row['hopping_rate']:.4f}")

    # fit volume vs n on log-log
    print()
    fits = {}
    for method in methods:
        pts = [(r["n"], r["volume"]) for r in results
               if r["method"] == method and r["volume"] > 0]
        if len(pts) >= 2:
            log_n = np.log([p[0] for p in pts])
            log_v = np.log([p[1] for p in pts])
            slope, intercept = np.polyfit(log_n, log_v, 1)
            fits[method] = {"slope": float(slope),
                            "intercept": float(intercept)}
            print(f"[fit {method}] volume ~ n^({slope:.3f})")

    # write JSON
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({
        "config": {"K": args.K, "n_list": ns, "methods": methods,
                   "seed": args.seed},
        "results": results,
        "fits": fits,
    }, indent=2))

    # write markdown
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RES-304 Triad Results",
        "",
        f"K = {args.K} random initializations per condition. "
        f"MaxCut, edge probability 0.5.",
        "",
        "## Basin metrics by n and method",
        "",
        "| n | method | volume | depth | boundary_dim | hopping_rate |",
        "|---|--------|--------|-------|--------------|--------------|",
    ]
    for r in results:
        lines.append(
            f"| {r['n']} | {r['method']} | {r['volume']:.4f} | "
            f"{r['depth']:.4f} | {r['boundary_dim']:.3f} | "
            f"{r['hopping_rate']:.4f} |"
        )
    lines.append("")
    lines.append("## Scaling fits (volume ~ n^slope)")
    lines.append("")
    lines.append("| method | slope | intercept |")
    lines.append("|--------|-------|-----------|")
    for m, f in fits.items():
        lines.append(f"| {m} | {f['slope']:.3f} | {f['intercept']:.3f} |")
    lines.append("")
    args.out_md.write_text("\n".join(lines))

    print()
    print(f"[write] {args.out_json}")
    print(f"[write] {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
