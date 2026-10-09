#!/usr/bin/env python3
"""
FEP ε-sweep runner.

Produces the numerical evidence for RES-600 §4 / RES-602 §6.

Fits log(residual) vs log(ε) under a chosen metric:
    --metric rmse (default)  — matches the O(ε) norm bound. Slope ≈ 1.
    --metric mse             — squared error. Slope ≈ 2.

Usage:
    python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64
    python scripts/run_fep_sweep.py --data trunk.npy --dim 128 --metric rmse
    python scripts/run_fep_sweep.py --simulate --out report_sweep.json
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

from resileos.substrate.reduction import VerifiableFEPReductionHead  # noqa: E402


def simulate_axiom_d(
    dim: int,
    seq_len: int,
    epsilon: float,
    psi_a: float = 0.5,
    psi_b: float = 1.5,
    f: float = 1.0,
    g_field: float = 0.85,
    dt: float = 0.01,
    seed: int = 0,
    embed_noise: float = 0.02,
) -> torch.Tensor:
    """Integrate Axiom D on the slow coordinate; embed in dim-dimensional ambient."""
    rng = np.random.default_rng(seed)
    m_e = g_field * psi_b / (psi_b - psi_a)

    psi = psi_b + epsilon
    traj = np.zeros(seq_len, dtype=np.float64)
    traj[0] = psi
    for t in range(1, seq_len):
        F = f * psi * (psi_a - psi) * (psi - psi_b)
        psi = psi + m_e * F * dt
        traj[t] = psi

    ambient = rng.standard_normal((seq_len, dim - 1)) * embed_noise
    full = np.concatenate([traj[:, None], ambient], axis=1)
    return torch.tensor(full[None, ...], dtype=torch.float32)


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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=None)
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--dim", type=int, default=128)
    p.add_argument("--seq-len", type=int, default=64)
    p.add_argument("--epsilons", default="0.1,0.05,0.02,0.01,0.005,0.001")
    p.add_argument("--g-field", type=float, default=0.85)
    p.add_argument("--metric", default="rmse", choices=["rmse", "mse"],
                   help="rmse matches O(ε) norm bound (slope≈1); "
                        "mse gives slope≈2")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    eps_list = [float(x) for x in args.epsilons.split(",")]

    basis = torch.zeros(args.dim, 1)
    basis[0, 0] = 1.0
    head = VerifiableFEPReductionHead(
        hidden_dim=args.dim, L_H_kernel=basis, rank=1,
    )

    if args.data:
        trunk_ref, label = load_trunk(Path(args.data), args.dim)
        print(f"[sweep] source: {label}")

        def factory(eps: float) -> torch.Tensor:
            t = trunk_ref.clone()
            t[:, 0, 0] = 1.5 + eps
            return t
    elif args.simulate:
        print(f"[sweep] source: simulated Axiom D  (dim={args.dim}, "
              f"T={args.seq_len}, G={args.g_field})")

        def factory(eps: float) -> torch.Tensor:
            return simulate_axiom_d(
                dim=args.dim, seq_len=args.seq_len, epsilon=eps,
                g_field=args.g_field, seed=0,
            )
    else:
        print("error: pass --data or --simulate", file=sys.stderr)
        return 2

    G = torch.ones(1, factory(eps_list[0]).shape[1], 1)
    result = head.sweep_epsilon(factory, eps_list, G, metric=args.metric)

    print()
    print(f"metric: {result['metric']}")
    print("eps        | residual")
    print("-" * 30)
    for eps, err in zip(result["epsilons"], result["errors"]):
        print(f"{eps:10.5f} | {err:.6e}")

    print()
    print(f"fitted slope  = {result['slope']:.4f}")
    print(f"intercept     = {result['intercept']:.4f}")
    print(f"r_squared     = {result['r_squared']:.6f}")

    slope = result["slope"]
    if result["metric"] == "rmse":
        if 0.85 <= slope <= 1.15:
            verdict = "consistent with linear O(ε) residual (RES-600 §4)"
            ok = True
        elif slope < 0.85:
            verdict = "sub-linear; check trajectory or discretization"
            ok = False
        elif slope > 1.15:
            verdict = "super-linear; check discretization error dominance"
            ok = False
        else:
            verdict = "inconclusive"
            ok = False
    else:  # mse
        if 1.85 <= slope <= 2.15:
            verdict = "consistent with O(ε) residual under MSE metric"
            ok = True
        else:
            verdict = "unexpected MSE scaling"
            ok = False

    print(f"verdict       = {verdict}")

    if args.out:
        payload = {
            "source": "simulate" if args.simulate else args.data,
            "dim": args.dim,
            "seq_len": args.seq_len,
            "g_field": args.g_field,
            **result,
            "verdict": verdict,
        }
        Path(args.out).write_text(json.dumps(payload, indent=2, default=float))
        print(f"\n[sweep] wrote {args.out}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
