#!/usr/bin/env python3
"""
End-to-end hybrid runner for Resileos-QAI.

Composes the full pipeline:

    ResidualCore (RES-200)
        └─ emits Packet (RES-201/202)
               └─ HDRIFTAdapter (RES-300)
                      ├─ build_moments (RES-301) — real FPE
                      ├─ holographic_drift
                      └─ SigmaGate (RES-303) + Abstention (RES-302)
                            └─ HybridValidator (RES-402)
                                   └─ report.json

Optionally trains the front-end encoder first (RES-401).
Frozen core never receives gradients.

Usage:
    python scripts/run_hybrid.py --config configs/example-run.json
    python scripts/run_hybrid.py --config configs/example-run.json --train
    python scripts/run_hybrid.py --config configs/example-run.json --out report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Allow running from repo root without install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.abstention import AbstentionThresholds
from resileos.adapter import HDRIFTAdapter
from resileos.core import CoreConfig, ResidualCore
from resileos.moments import Seeds
from resileos.sigma import SigmaGate
from resileos.training import FrontEndEncoder, TrainingConfig, train
from resileos.validation import HybridValidator, RunConfig, save_report


# ── config loading ────────────────────────────────────────────────────────
def load_run_config(path: Path) -> RunConfig:
    raw = json.loads(path.read_text())
    raw["seeds"] = Seeds(**raw["seeds"])
    raw["seed_list"] = tuple(raw["seed_list"])
    return RunConfig(**raw)


# ── data generation (replace with real weight/feature blocks) ─────────────
def make_block(seed: int, m: int, n: int) -> np.ndarray:
    """Deterministic test block. Swap for real data in production."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((m, n))


def make_x_enc(seed: int, step: int, dim: int) -> np.ndarray:
    rng = np.random.default_rng(seed * 100_000 + step)
    v = rng.standard_normal(dim)
    return v / (np.linalg.norm(v) + 1e-12)


# ── core+adapter+validator assembly ───────────────────────────────────────
def build_stack(cfg: RunConfig,
                m: int = 32,
                n: int = 32,
                core_seed: int = 0,
                encoder_seed: int = 0,
                ) -> tuple[ResidualCore, FrontEndEncoder, HDRIFTAdapter, HybridValidator]:
    r = 8  # latent rank; must stay <= min(m, n)

    core = ResidualCore(CoreConfig(m=m, n=n, r=r), seed=core_seed)
    encoder = FrontEndEncoder(m=m, n=n, r=r, seed=encoder_seed)

    adapter = HDRIFTAdapter(
        dim=cfg.dim,
        seeds=cfg.seeds,
        drift_ratio_floor=cfg.drift_ratio_floor,
    )
    thresholds = AbstentionThresholds(
        E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low,
    )
    gate = SigmaGate(E_sigma=cfg.E_sigma, k=cfg.sigma1_k)
    validator = HybridValidator(cfg, adapter, thresholds, sigma_gate=gate)

    return core, encoder, adapter, validator


# ── packet producer for the validator ─────────────────────────────────────
def make_packet_fn(core: ResidualCore,
                   encoder: FrontEndEncoder,
                   m: int,
                   n: int,
                   ):
    """
    Returns a callable (seed, step) -> Packet that:
      1. Generates a weight block for the seed.
      2. Runs the trained encoder to produce binary factors.
      3. Runs the frozen core step to produce a conformant packet.
    """
    def packet_fn(seed: int, step: int):
        W = make_block(seed + step * 1000, m, n)

        enc_out = encoder.forward(W)
        Ub = enc_out["Ub"]
        Vb = enc_out["Vb"]

        # F_res proxy: signed reconstruction residual magnitude direction.
        R = W - Ub @ Vb
        F_res = float(np.mean(R))

        return core.step(
            W=W,
            mu=int(step % 2),         # replaced by real parity stream in prod
            F_res=F_res,
            theta_hi=0.0,
            theta_lo=0.0,
            DeltaS=float(1.0 / (1.0 + np.linalg.norm(R))),
        )
    return packet_fn


# ── main ──────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Run the Resileos-QAI hybrid pipeline.")
    p.add_argument("--config", required=True, help="Path to run config JSON")
    p.add_argument("--out", default="report.json", help="Output report path")
    p.add_argument("--train", action="store_true", help="Train the front-end first")
    p.add_argument("--epochs", type=int, default=20, help="Training epochs")
    p.add_argument("--horizon", type=int, default=32, help="Steps per seed")
    p.add_argument("--m", type=int, default=32, help="Weight block rows")
    p.add_argument("--n", type=int, default=32, help="Weight block cols")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip adapter acceptance tests")
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"error: config not found: {cfg_path}", file=sys.stderr)
        return 2

    cfg = load_run_config(cfg_path)
    cfg.assert_declared()

    print(f"[runner] packet_version = {cfg.packet_version}")
    print(f"[runner] dim            = {cfg.dim}")
    print(f"[runner] seeds          = {cfg.seeds}")
    print(f"[runner] X, Y           = {cfg.X}, {cfg.Y}")
    print(f"[runner] seed_list      = {cfg.seed_list}")

    core, encoder, adapter, validator = build_stack(
        cfg, m=args.m, n=args.n, core_seed=0, encoder_seed=0,
    )

    # ── optional training pass ────────────────────────────────────────────
    if args.train:
        print(f"[runner] training {args.epochs} epochs (front-end only)")
        W_train = [make_block(s, args.m, args.n) for s in range(4)]
        W_hold = [make_block(100 + s, args.m, args.n) for s in range(2)]

        tcfg = TrainingConfig(
            epochs=args.epochs,
            lr=0.05,
            lam=1e-4,
            scar_var_floor=cfg.scar_var_floor,
            deltaS_range_floor=cfg.deltaS_range_floor,
        )
        train_report = train(core, encoder, W_train, W_hold, tcfg)
        acc = train_report["acceptance"]
        print(f"[runner] training conformant = {acc['conformant']}")
        print(f"[runner]   scar variance     = {acc['scar_energy_variance']:.6g}")
        print(f"[runner]   ΔS range          = {acc['DeltaS_range']:.6g}")

        if not acc["conformant"]:
            print("[runner] warning: training floors not met", file=sys.stderr)

    # ── adapter acceptance (RES-301) ──────────────────────────────────────
    if not args.no_verify:
        sample_packet = core.step(make_block(0, args.m, args.n))
        x_sample = [make_x_enc(0, t, cfg.dim) for t in range(64)]
        diag = adapter.verify(sample_packet, x_sample)
        print(f"[runner] adapter cos         = {diag['cos']:.4f} "
              f"({'ok' if diag['cos_ok'] else 'FAIL'})")
        print(f"[runner] drift variance     = {diag['drift_ratio_variance']:.6g} "
              f"({'ok' if diag['drift_ratio_variance_ok'] else 'FAIL'})")
        print(f"[runner] drift SNR          = {diag['drift_ratio_snr']:.4f}")
        if not diag["pass"]:
            print("[runner] warning: adapter acceptance failed", file=sys.stderr)

    # ── validation run ────────────────────────────────────────────────────
    print(f"[runner] validating over {len(cfg.seed_list)} seeds, "
          f"horizon={args.horizon}")

    packet_fn = make_packet_fn(core, encoder, args.m, args.n)

    def x_fn(seed: int, step: int) -> np.ndarray:
        return make_x_enc(seed, step, cfg.dim)

    def recon_err_fn(packet) -> float:
        get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))
        return float(abs(get("F_res")))

    report = validator.run(
        packet_fn=packet_fn,
        x_fn=x_fn,
        horizon_len=args.horizon,
        recon_err_fn=recon_err_fn,
    )

    save_report(report, args.out)

    agg = report["aggregate"]
    print(f"[runner] NRMSE reduction    = {agg['nrmse_reduction_mean_pct']:.3f}% "
          f"(± {agg['nrmse_reduction_std_pct']:.3f})")
    print(f"[runner] horizon extension  = {agg['horizon_extension_mean']:.2f} steps "
          f"(± {agg['horizon_extension_std']:.2f})")
    print(f"[runner] conformant         = {report['conformant']}")
    print(f"[runner] report written to  = {args.out}")

    return 0 if report["conformant"] else 1


if __name__ == "__main__":
    sys.exit(main())
