#!/usr/bin/env python3
"""
FEP ε-sweep runner.

Three modes:

    --simulate              ideal Axiom D trajectory (baseline)
    --stress                stress-tested Axiom D trajectory
    --data <path.npy>       user-supplied trajectory

The stress mode runs the sweep at multiple stress levels and prints the
slope at each, so you can see whether the linear O(ε) bound holds as
conditions degrade from ideal.

Usage:
    python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64
    python scripts/run_fep_sweep.py --stress --dim 128 --seq-len 64
    python scripts/run_fep_sweep.py --data trunk.npy --dim 128
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

from resileos.substrate.reduction import (  # noqa: E402
    VerifiableFEPReductionHead,
    simulate_axiom_d,
)


def load_trunk(path: Path, dim: int) -> tuple[torch.Tensor, str]:
    arr = np.load(str(path))
    if arr.ndim == 2:
        arr = arr[None, ...]
    if arr.ndim != 3:
        raise ValueError(f"expected [T,D] or [K,T,D], got {arr.shape}")
    if arr.shape[-1] != dim:
        raise ValueError(f"last dim {arr.shape[-1]} != --dim {dim}")
    trunk = torch.tensor(arr.mean(axis=0)[None, ...], dtype=torch.float32)
    return trunk, f"{path} (K={arr.shape[0]}, T={arr.shape[1]}, D={arr.shape[2]})"


def _verdict(slope: float, metric: str) -> tuple[str, bool]:
    if metric == "rmse":
        if 0.85 <= slope <= 1.15:
            return "consistent with linear O(ε) residual (RES-600 §4)", True
        if slope < 0.85:
            return "sub-linear; check trajectory or discretization", False
        return "super-linear; check discretization error dominance", False
    if 1.85 <= slope <= 2.15:
        return "consistent with O(ε) residual under MSE metric", True
    return "unexpected MSE scaling", False


def _run_one(head, factory, eps_list, metric):
    G = torch.ones(1, factory(eps_list[0]).shape[1], 1)
    return head.sweep_epsilon(factory, eps_list, G, metric=metric)


def _print_result(result, header=None):
    if header:
        print(f"\n--- {header} ---")
    print(f"metric: {result['metric']}")
    print("eps        | residual")
    print("-" * 30)
    for eps, err in zip(result["epsilons"], result["errors"]):
        print(f"{eps:10.5f} | {err:.6e}")
    print(f"fitted slope  = {result['slope']:.4f}")
    print(f"intercept     = {result['intercept']:.4f}")
    print(f"r_squared     = {result['r_squared']:.6f}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=None)
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--stress", action="store_true")
    p.add_argument("--dim", type=int, default=128)
    p.add_argument("--seq-len", type=int, default=64)
    p.add_argument("--epsilons", default="0.1,0.05,0.02,0.01,0.005,0.001")
    p.add_argument("--g-field", type=float, default=0.85)
    p.add_argument("--metric", default="rmse", choices=["rmse", "mse"])
    p.add_argument("--out", default=None)
    args = p.parse_args()

    eps_list = [float(x) for x in args.epsilons.split(",")]

    basis = torch.zeros(args.dim, 1)
    basis[0, 0] = 1.0
    head = VerifiableFEPReductionHead(
        hidden_dim=args.dim, L_H_kernel=basis, rank=1,
    )

    # ── mode: data ───────────────────────────────────────────────────────
    if args.data:
        trunk_ref, label = load_trunk(Path(args.data), args.dim)
        print(f"[sweep] source: {label}")

        def factory(eps: float) -> torch.Tensor:
            t = trunk_ref.clone()
            t[:, 0, 0] = 1.5 + eps
            return t

        result = _run_one(head, factory, eps_list, args.metric)
        _print_result(result)
        verdict, ok = _verdict(result["slope"], args.metric)
        print(f"verdict       = {verdict}")

        if args.out:
            Path(args.out).write_text(json.dumps({
                "source": args.data, "dim": args.dim,
                "g_field": args.g_field, **result, "verdict": verdict,
            }, indent=2, default=float))
            print(f"\n[sweep] wrote {args.out}")
        return 0 if ok else 1

    # ── mode: simulate ───────────────────────────────────────────────────
    if args.simulate:
        print(f"[sweep] source: simulated Axiom D  (dim={args.dim}, "
              f"T={args.seq_len}, G={args.g_field})")

        def factory(eps: float) -> torch.Tensor:
            return simulate_axiom_d(
                dim=args.dim, seq_len=args.seq_len, epsilon=eps,
                g_field=args.g_field, seed=0,
            )

        result = _run_one(head, factory, eps_list, args.metric)
        _print_result(result)
        verdict, ok = _verdict(result["slope"], args.metric)
        print(f"verdict       = {verdict}")

        if args.out:
            Path(args.out).write_text(json.dumps({
                "source": "simulate", "dim": args.dim,
                "seq_len": args.seq_len, "g_field": args.g_field,
                **result, "verdict": verdict,
            }, indent=2, default=float))
            print(f"\n[sweep] wrote {args.out}")
        return 0 if ok else 1

    # ── mode: stress ─────────────────────────────────────────────────────
    if args.stress:
        print(f"[sweep] source: stress-tested Axiom D  (dim={args.dim}, "
              f"T={args.seq_len}, G={args.g_field})")
        print()
        print("Stress levels (off_manifold_frac, g_ramp, dt_coarse):")
        print("-" * 60)

        # 5 levels from ideal to heavily stressed
        levels = [
            (0.0, 0.0, 1.0),   # ideal (sanity: must match --simulate)
            (0.1, 0.05, 2.0),  # mild
            (0.2, 0.10, 4.0),  # moderate
            (0.3, 0.20, 6.0),  # strong
            (0.5, 0.30, 8.0),  # extreme
        ]
        slopes = []
        all_results = []

        for i, (om, gr, dtc) in enumerate(levels):
            def factory(eps: float, om=om, gr=gr, dtc=dtc) -> torch.Tensor:
                return simulate_axiom_d(
                    dim=args.dim, seq_len=args.seq_len, epsilon=eps,
                    g_field=args.g_field, seed=0,
                    off_manifold_frac=om, g_ramp=gr, dt_coarse=dtc,
                )

            result = _run_one(head, factory, eps_list, args.metric)
            slopes.append(result["slope"])
            all_results.append({
                "level": i,
                "off_manifold_frac": om,
                "g_ramp": gr,
                "dt_coarse": dtc,
                **result,
            })
            print(f"  L{i}  om={om:.2f}  gr={gr:.2f}  dtc={dtc:.1f}  "
                  f"->  slope={result['slope']:.4f}  "
                  f"r²={result['r_squared']:.6f}")

        print()
        print("Summary:")
        print(f"  slope range: {min(slopes):.4f} .. {max(slopes):.4f}")
        drift = max(slopes) - min(slopes)
        if drift < 0.15:
            print(f"  drift = {drift:.4f}  ->  bound holds under stress")
            ok = True
        elif drift < 0.4:
            print(f"  drift = {drift:.4f}  ->  bound degrades under stress")
            ok = True
        else:
            print(f"  drift = {drift:.4f}  ->  bound does not hold at high stress")
            ok = False

        if args.out:
            Path(args.out).write_text(json.dumps({
                "source": "stress", "dim": args.dim,
                "seq_len": args.seq_len, "g_field": args.g_field,
                "levels": all_results,
                "slope_range": [min(slopes), max(slopes)],
                "drift": drift,
            }, indent=2, default=float))
            print(f"\n[sweep] wrote {args.out}")
        return 0 if ok else 1

    print("error: pass --simulate, --stress, or --data", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
