#!/usr/bin/env python3
"""
Outer-loop substrate evolution: search r, n_loops, feature_mask by
carrier val loss on a synthetic task.

For each candidate config:
  1. Instantiate a fresh ResidualCore with the candidate's r and n_loops.
  2. Build a SubstrateCarrier with extra_dim matching the enabled
     non-packet features.
  3. Train the carrier on a training split.
  4. Measure val loss.

No gradient touches the substrate. Frozen contracts preserved.

The reward is a *toy* carrier val loss, not a claim about any real task.
Its purpose is to demonstrate that the outer loop can search the
substrate configuration space and produce a real ordering.

Usage:
    python scripts/run_evolution.py
    python scripts/run_evolution.py --strategy random --budget 16
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
from resileos.evolution import EvolutionLoop, SubstrateConfig


M, N = 8, 8
D_OUT = 16
SIGMA = 0.5
N_TRAIN = 256
N_VAL = 64
CARRIER_STEPS = 200
CARRIER_LR = 1e-3
HIDDEN = 128


# ── feature pack per config ─────────────────────────────────────────────
def _extra_dim_for(mask: tuple[str, ...]) -> int:
    """How many extra scalars the non-packet features contribute."""
    d = 0
    if "csi" in mask:
        d += 3      # csi value, R, anisotropy (approximated by 0 on synthetic)
    if "order_parameter" in mask:
        d += 1
    if "direction" in mask:
        d += D_OUT  # a low-dim placeholder direction
    return d


def _extra_vector(mask: tuple[str, ...], rng: np.random.Generator) -> np.ndarray:
    """Synthetic extra features. Real integration would pull these from
    Titanos / CSI state / DirectionalHDRIFT. For the toy A/B, they are
    noise so the carrier has to learn to ignore or use them."""
    return rng.standard_normal(_extra_dim_for(mask)).astype(np.float64)


# ── evaluate one config ─────────────────────────────────────────────────
def make_evaluator(base_seed: int = 0):
    # Frozen base "model": A @ x, target has a per-example offset.
    rng = np.random.default_rng(base_seed)
    A = rng.standard_normal((D_OUT, D_OUT))
    del A  # not used directly in the synthetic task; kept for reference

    def evaluate(cfg: SubstrateConfig) -> float:
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
                    b = carrier(packet, extra=obs if extra_dim == D_OUT else extra)
                else:
                    b = carrier(packet)
                # The task: predict the correction c - obs, so the base
                # model's output plus the carrier's bias approximates c.
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
                    b = carrier(packet, extra=obs if extra_dim == D_OUT else extra)
                else:
                    b = carrier(packet)
                target = torch.from_numpy(c - obs).float()
                losses.append(float(((b - target) ** 2).mean()))
            val_loss = float(np.mean(losses))
        return val_loss
    return evaluate


# ── main ────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", default="grid", choices=["grid", "random"])
    p.add_argument("--budget", type=int, default=16)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "report_evolution.json"))
    args = p.parse_args()

    loop = EvolutionLoop(
        r_values=(4, 6, 8),
        n_loops_values=(4, 8, 12),
        feature_masks=(
            ("packet",),
            ("packet", "csi"),
            ("packet", "csi", "order_parameter"),
            ("packet", "csi", "order_parameter", "direction"),
        ),
        strategy=args.strategy,
        budget=args.budget,
        seed=args.seed,
    )

    print(f"strategy={args.strategy}  candidates={len(loop)}")

    evaluator = make_evaluator(base_seed=args.seed)
    for i, cfg in enumerate(loop, 1):
        reward = evaluator(cfg)
        loop.observe(cfg, reward)
        print(f"  [{i:2d}/{len(loop)}] r={cfg.r:2d} n_loops={cfg.n_loops:2d} "
              f"mask={','.join(cfg.feature_mask):30s} val_loss={reward:.4f}")

    summary = loop.summary()
    print()
    print("=== summary ===")
    print(f"  evaluated:    {summary['n_evaluated']}")
    print(f"  reward min:   {summary['reward_min']:.4f}")
    print(f"  reward max:   {summary['reward_max']:.4f}")
    print(f"  reward mean:  {summary['reward_mean']:.4f}")
    print(f"  best config:  r={summary['best_config']['r']} "
          f"n_loops={summary['best_config']['n_loops']} "
          f"mask={summary['best_config']['feature_mask']}")

    report = {
        "strategy": args.strategy,
        "budget": args.budget,
        "seed": args.seed,
        "summary": summary,
        "history": [
            {
                "r": rec.config.r,
                "n_loops": rec.config.n_loops,
                "feature_mask": list(rec.config.feature_mask),
                "reward": rec.reward,
            }
            for rec in loop.history()
        ],
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
