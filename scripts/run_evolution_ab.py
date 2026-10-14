#!/usr/bin/env python3
"""
A/B: EvolutionLoop (grid) vs OscillatorOrientedSearch on the same
toy carrier reward.

Both searchers share the same discrete grid, the same budget, and the
same evaluator. The measurement is: does the oscillator-biased order
reach a better best-so-far at each step than grid order?

Reports:
    - best reward after K steps for each
    - coverage at K
    - best reward as a function of step

Usage:
    python scripts/run_evolution_ab.py --iterations 12
    python scripts/run_evolution_ab.py --iterations 20 --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.carrier import SubstrateCarrier
from resileos.core import CoreConfig, ResidualCore
from resileos.evolution import EvolutionLoop
from resileos.evolution_oscillator import OscillatorOrientedSearch


M, N = 8, 8
D_OUT = 16
SIGMA = 0.5
N_TRAIN = 256
N_VAL = 64
CARRIER_STEPS = 200
CARRIER_LR = 1e-3
HIDDEN = 128


# ── feature pack (duplicated from run_evolution.py) ─────────────────────
def _extra_dim_for(mask: tuple) -> int:
    d = 0
    if "csi" in mask:
        d += 3
    if "order_parameter" in mask:
        d += 1
    if "direction" in mask:
        d += D_OUT
    return d


def _extra_vector(mask: tuple, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(_extra_dim_for(mask)).astype(np.float64)


def make_evaluator(base_seed: int = 0):
    rng = np.random.default_rng(base_seed)

    def evaluate(cfg) -> float:
        torch.manual_seed(base_seed)
        rng_local = np.random.default_rng(base_seed + 1)

        core = ResidualCore(
            CoreConfig(m=M, n=N, r=cfg.r, n_residual_layers=cfg.n_loops),
            seed=base_seed,
        )
        extra_dim = _extra_dim_for(cfg.feature_mask)

        def make_sample(idx: int):
            W = rng_local.standard_normal((M, N))
            packet = core.step(W, mu=int(idx % 2), F_res=0.1, DeltaS=0.5)
            c = rng_local.standard_normal(D_OUT)
            obs = c + SIGMA * rng_local.standard_normal(D_OUT)
            extra = _extra_vector(cfg.feature_mask, rng_local)
            return packet, extra if extra_dim > 0 else None, obs, c

        train = [make_sample(i) for i in range(N_TRAIN)]
        val = [make_sample(i) for i in range(N_VAL)]

        carrier = SubstrateCarrier(
            m=M, n=N, r=cfg.r,
            output_shape=(D_OUT,),
            hidden_dim=HIDDEN,
            n_layers=2,
            extra_dim=extra_dim,
            seed=base_seed,
        )
        opt = torch.optim.Adam(carrier.parameters(), lr=CARRIER_LR)

        step = 0
        while step < CARRIER_STEPS:
            opt.zero_grad()
            total = torch.zeros(())
            count = 0
            for packet, extra, obs, c in train:
                if extra_dim > 0:
                    b = carrier(packet,
                                extra=obs if extra_dim == D_OUT else extra)
                else:
                    b = carrier(packet)
                target = torch.from_numpy(c - obs).float()
                total = total + ((b - target) ** 2).mean()
                count += 1
                if count >= 32:
                    break
            (total / max(count, 1)).backward()
            opt.step()
            step += 1

        with torch.no_grad():
            losses = []
            for packet, extra, obs, c in val:
                if extra_dim > 0:
                    b = carrier(packet,
                                extra=obs if extra_dim == D_OUT else extra)
                else:
                    b = carrier(packet)
                target = torch.from_numpy(c - obs).float()
                losses.append(float(((b - target) ** 2).mean()))
            return float(np.mean(losses))

    return evaluate


# ── main ────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--iterations", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "report_evolution_ab.json"))
    args = p.parse_args()

    grid_kwargs = dict(
        r_values=(4, 6, 8, 12),
        n_loops_values=(4, 8, 12),
        feature_masks=(
            ("packet",),
            ("packet", "csi"),
            ("packet", "csi", "order_parameter"),
            ("packet", "csi", "order_parameter", "direction"),
        ),
    )

    evaluator = make_evaluator(base_seed=args.seed)

    print(f"iterations={args.iterations}  seed={args.seed}")

    # Grid
    grid = EvolutionLoop(
        **grid_kwargs, strategy="grid", budget=args.iterations,
    )
    grid.run(evaluator)
    grid_bsf = []
    cur = float("inf")
    for rec in grid.history():
        cur = min(cur, rec.reward)
        grid_bsf.append(cur)

    # Oriented
    oriented = OscillatorOrientedSearch(
        **grid_kwargs, budget=args.iterations, seed=args.seed,
    )
    oriented.run(evaluator, iterations=args.iterations)
    oriented_bsf = oriented.best_so_far()

    # Side-by-side
    print()
    print("step | grid_best | oriented_best | delta")
    print("-" * 48)
    for i in range(max(len(grid_bsf), len(oriented_bsf))):
        g = grid_bsf[i] if i < len(grid_bsf) else None
        o = oriented_bsf[i] if i < len(oriented_bsf) else None
        d = ""
        if g is not None and o is not None:
            d = f"{o - g:+.4f}"
        print(f"{i + 1:4d} | {('%.4f' % g) if g is not None else '   -   '} | "
              f"{('%.4f' % o) if o is not None else '   -   '} | {d:>8}")

    g_final = grid_bsf[-1] if grid_bsf else float("nan")
    o_final = oriented_bsf[-1] if oriented_bsf else float("nan")
    print()
    print(f"grid best at K:      {g_final:.4f}")
    print(f"oriented best at K:  {o_final:.4f}")
    print(f"delta:               {o_final - g_final:+.4f}")
    print()
    print(f"grid coverage:       {len(grid.history())}/{len(grid)}")
    print(f"oriented coverage:   {oriented.n_visited()}/{len(oriented._grid)}")
    print(f"oriented field R:    {oriented.field.order_parameter():.4f}")

    report = {
        "iterations": args.iterations,
        "seed": args.seed,
        "grid_best_so_far": grid_bsf,
        "oriented_best_so_far": oriented_bsf,
        "grid_best_config": {
            "r": grid.best().config.r,
            "n_loops": grid.best().config.n_loops,
            "feature_mask": list(grid.best().config.feature_mask),
        },
        "oriented_best_config": {
            "r": oriented.best().config.r,
            "n_loops": oriented.best().config.n_loops,
            "feature_mask": list(oriented.best().config.feature_mask),
        },
        "oriented_field_R": oriented.field.order_parameter(),
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
