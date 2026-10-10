#!/usr/bin/env python3
"""
FEP ε-sweep runner.

Modes:
    --simulate              ideal Axiom D trajectory (baseline)
    --stress                stress-tested Axiom D trajectory (L0..L4)
    --data <path.npy>       real trajectory file

Data mode behavior depends on the file shape:

    [K, T, D] with K >= 3   real ε sweep across K trajectories. ε_k is
                            the actual initial deviation of trajectory k
                            from an estimated Ψ_B (mean of last 10% on
                            coordinate 0). If a sidecar JSON with an
                            "epsilons" list exists next to the .npy, it
                            is used as the ε labels; otherwise the
                            trajectory-derived values are used.

    [T, D] or K < 3         single-trajectory mode. Reports the ODE
                            residual at the actual ε and refuses to
                            compute a slope. A slope requires >= 3
                            trajectories with different initial deviations.

Usage:
    python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64
    python scripts/run_fep_sweep.py --stress --dim 128 --seq-len 64 --metric rmse
    python scripts/run_fep_sweep.py --stress --dim 128 --seq-len 64 --metric mse
    python scripts/run_fep_sweep.py --data configs/trunk_axiom_d.npy --dim 128
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
    coherence_schedule,
    simulate_axiom_d,
)

MIN_TRAJ_FOR_SWEEP = 3


# ── loading ─────────────────────────────────────────────────────────────
def load_trunk(path: Path, dim: int):
    """
    Load a real trajectory file and its optional sidecar JSON.

    Returns:
        (arr [K, T, D] float32, label str, sidecar dict or {})
    """
    arr = np.load(str(path))
    if arr.ndim == 2:
        arr = arr[None, ...]
    if arr.ndim != 3:
        raise ValueError(f"expected [T,D] or [K,T,D], got {arr.shape}")
    if arr.shape[-1] != dim:
        raise ValueError(f"last dim {arr.shape[-1]} != --dim {dim}")
    arr = arr.astype(np.float32)

    sidecar = {}
    sidecar_path = path.with_suffix(".json")
    if sidecar_path.exists():
        try:
            sidecar = json.loads(sidecar_path.read_text())
        except Exception:
            sidecar = {}

    label = (
        f"{path} (K={arr.shape[0]}, T={arr.shape[1]}, D={arr.shape[2]})"
    )
    return arr, label, sidecar


def estimate_psi_b(trajectories: np.ndarray, tail_frac: float = 0.1) -> float:
    """Estimate Ψ_B from the tail of the trajectories on coordinate 0."""
    _, T, _ = trajectories.shape
    tail = max(1, int(T * tail_frac))
    return float(np.mean(trajectories[:, -tail:, 0]))


# ── verdicts ────────────────────────────────────────────────────────────
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


def _run_one(head, factory, eps_list, metric, G=None):
    sample = factory(eps_list[0])
    if G is None:
        G = torch.ones(1, sample.shape[1], 1)
    return head.sweep_epsilon(factory, eps_list, G, metric=metric)


# ── data mode ───────────────────────────────────────────────────────────
def run_data_mode(args, head) -> int:
    arr, label, sidecar = load_trunk(Path(args.data), args.dim)
    K, T, D = arr.shape
    print(f"[sweep] source: {label}")

    psi_b_est = estimate_psi_b(arr)
    print(f"[sweep] estimated Ψ_B = {psi_b_est:.6f} "
          f"(coordinate 0, mean of last 10%)")

    G = torch.full((1, T, 1), float(args.g_field), dtype=torch.float32)
    print(f"[sweep] G (constant, --g-field) = {args.g_field}")

    # Prefer sidecar epsilons if present.
    bank_eps = None
    if sidecar.get("epsilons") and len(sidecar["epsilons"]) == K:
        bank_eps = np.asarray(sidecar["epsilons"], dtype=np.float64)
        print(f"[sweep] using sidecar ε labels ({K} values)")

    if K < MIN_TRAJ_FOR_SWEEP:
        print()
        print(f"[sweep] only {K} trajectory(ies); "
              f"{MIN_TRAJ_FOR_SWEEP} required for a sweep.")
        trunk = torch.tensor(arr[0:1], dtype=torch.float32)
        eps_actual = float(arr[0, 0, 0] - psi_b_est)
        with torch.no_grad():
            _, err = head(trunk, G)
        residual = float(err.item()) ** 0.5
        print(f"  actual ε = {eps_actual:.6f}")
        print(f"  residual (rmse) = {residual:.6e}")
        if args.out:
            Path(args.out).write_text(json.dumps({
                "source": args.data, "K": K, "T": T, "D": D,
                "psi_b_estimate": psi_b_est,
                "actual_epsilon": eps_actual,
                "residual_rmse": residual,
                "slope": None,
                "note": f"single-trajectory mode; K < {MIN_TRAJ_FOR_SWEEP}",
            }, indent=2, default=float))
            print(f"\n[sweep] wrote {args.out}")
        return 0

    if bank_eps is not None:
        order = np.argsort(bank_eps)
        eps_use = bank_eps[order]
        idx_use = order
    else:
        eps_real = arr[:, 0, 0] - psi_b_est
        order = np.argsort(eps_real)
        eps_use = eps_real[order]
        idx_use = order
        if np.any(eps_use <= 0):
            print(f"[sweep] warning: {int((eps_use <= 0).sum())} "
                  f"non-positive ε from trajectory; skipped.")
            mask = eps_use > 0
            if int(mask.sum()) < MIN_TRAJ_FOR_SWEEP:
                print("[sweep] insufficient positive-ε trajectories.")
                return 2
            eps_use = eps_use[mask]
            idx_use = idx_use[mask]

    errs = []
    for k_idx in idx_use:
        trunk = torch.tensor(arr[k_idx:k_idx + 1], dtype=torch.float32)
        with torch.no_grad():
            _, err = head(trunk, G)
        mse = max(float(err.item()), 1e-30)
        errs.append(mse ** 0.5 if args.metric == "rmse" else mse)
    err_arr = np.asarray(errs, dtype=np.float64)

    log_eps = np.log(eps_use)
    log_err = np.log(err_arr)
    slope, intercept = np.polyfit(log_eps, log_err, 1)
    pred = slope * log_eps + intercept
    ss_res = float(np.sum((log_err - pred) ** 2))
    ss_tot = float(np.sum((log_err - log_err.mean()) ** 2)) + 1e-30
    r_squared = 1.0 - ss_res / ss_tot

    result = {
        "metric": args.metric,
        "epsilons": eps_use.tolist(),
        "errors": err_arr.tolist(),
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(r_squared),
    }
    _print_result(result)
    verdict, ok = _verdict(slope, args.metric)
    print(f"verdict       = {verdict}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "source": args.data, "K": K, "T": T, "D": D,
            "psi_b_estimate": psi_b_est,
            "g_field_used": args.g_field,
            "eps_source": "sidecar" if bank_eps is not None else "trajectory",
            **result,
            "verdict": verdict,
        }, indent=2, default=float))
        print(f"\n[sweep] wrote {args.out}")
    return 0 if ok else 1


# ── main ────────────────────────────────────────────────────────────────
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

    # ── data mode ───────────────────────────────────────────────────────
    if args.data:
        return run_data_mode(args, head)

    # ── simulate mode ───────────────────────────────────────────────────
    if args.simulate:
        print(f"[sweep] source: simulated Axiom D  (dim={args.dim}, "
              f"T={args.seq_len}, G={args.g_field})")

        def factory(eps: float) -> torch.Tensor:
            return simulate_axiom_d(
                dim=args.dim, seq_len=args.seq_len, epsilon=eps,
                g_field=args.g_field, seed=0,
            )

        G = coherence_schedule(args.seq_len, g_field=args.g_field, g_ramp=0.0)
        result = _run_one(head, factory, eps_list, args.metric, G=G)
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

    # ── stress mode ─────────────────────────────────────────────────────
    if args.stress:
        print(f"[sweep] source: stress-tested Axiom D  (dim={args.dim}, "
              f"T={args.seq_len}, G={args.g_field})")
        print()
        print("Stress levels (off_manifold_frac, g_ramp, dt_coarse):")
        print("-" * 60)

        levels = [
            (0.0, 0.0, 1.0),
            (0.1, 0.05, 2.0),
            (0.2, 0.10, 4.0),
            (0.3, 0.20, 6.0),
            (0.5, 0.30, 8.0),
        ]
        slopes = []
        all_results = []

        for i, (om, gr, dtc) in enumerate(levels):
            def factory(eps: float, om=om, gr=gr, dtc=dtc):
                return simulate_axiom_d(
                    dim=args.dim, seq_len=args.seq_len, epsilon=eps,
                    g_field=args.g_field, seed=0,
                    off_manifold_frac=om, g_ramp=gr, dt_coarse=dtc,
                )

            G = coherence_schedule(args.seq_len, g_field=args.g_field,
                                   g_ramp=gr)
            result = _run_one(head, factory, eps_list, args.metric, G=G)
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
                "metric": args.metric,
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
