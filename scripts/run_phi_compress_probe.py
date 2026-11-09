#!/usr/bin/env python3
"""φ-compress orientation probe (RES-401 §4 / RES-501 §8 item 1).

Measures whether the field's R trajectory survives rank contraction.
The existing unit test (`test_phi_orientation_transfer.py`) verifies that
θ/ω of kept oscillators are preserved mechanically. This probe verifies
the consequence: does R stay in its pre-contract band, and if it drifts,
how many steps until it recovers?

Three conditions measured:

    baseline   phi_compress_enabled = False, r = 8, N steps
    off        phi_compress_enabled = False, r = 8, then contracted
               to r = 4 manually, N steps (measures the "rebuild without
               transfer" failure mode)
    on         phi_compress_enabled = True, fires at step K, N steps
               (measures the actual transfer path)

Pass condition (RES-401 §4):

    |mean(post) - mean(pre)| < 0.05
    AND recovery_time < 10 steps

If both hold, orientation transfer works and the compression mechanism
is validated. If either fails, the rebuild loses orientation — that is
a real finding, not a bug to explain away.

Usage:
    PYTHONPATH=src python scripts/run_phi_compress_probe.py \
        --steps 200 --dim 512 --m 22 --n 23 --seed 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.pipeline import LanguagePipeline, PipelineConfig  # noqa: E402
from resileos.phi_compress import contract_rank  # noqa: E402


# ── config ─────────────────────────────────────────────────────────────


def _cfg(
    *,
    dim: int,
    m: int,
    n: int,
    r: int,
    phi_compress_enabled: bool,
    phi_compress_warmup: int = 0,
    phi_compress_min_R: float = 0.0,
    phi_compress_min_rank: int = 4,
    seed: int = 0,
) -> PipelineConfig:
    return PipelineConfig(
        dim=dim,
        m=m,
        n=n,
        r=r,
        n_residual_layers=4,
        reaper_n_saved=4,
        phi_compress_enabled=phi_compress_enabled,
        phi_compress_warmup=phi_compress_warmup,
        phi_compress_min_R=phi_compress_min_R,
        phi_compress_min_rank=phi_compress_min_rank,
        oscillator_kappa=1.0,
        oscillator_alpha=0.5,
        oscillator_dt=0.1,
        seed=seed,
    )


# ── measurement ────────────────────────────────────────────────────────


def _run(
    pipeline: LanguagePipeline,
    tokens: list[int],
    steps: int,
) -> list[float]:
    """Run N steps, return the R trajectory."""
    rs: list[float] = []
    for i in range(steps):
        # Use a small deterministic token window per step so the pipeline
        # advances without depending on a corpus.
        window = tokens[(i % 8) : (i % 8) + 8]
        if not window:
            window = tokens[:8]
        result = pipeline.step(window)
        rs.append(float(result.order_parameter))
    return rs


def _band(rs: list[float]) -> tuple[float, float]:
    arr = np.asarray(rs, dtype=float)
    return float(arr.mean()), float(arr.std(ddof=0))


def _recovery_steps(
    rs: list[float],
    pre_mean: float,
    pre_std: float,
    fire_step: int,
    threshold_sigma: float = 2.0,
) -> Optional[int]:
    """Steps after fire_step until R returns to within threshold_sigma of
    the pre-contract band. Returns None if it never does."""
    band_lo = pre_mean - threshold_sigma * pre_std
    band_hi = pre_mean + threshold_sigma * pre_std
    for j in range(fire_step, len(rs)):
        if band_lo <= rs[j] <= band_hi:
            return j - fire_step
    return None


# ── conditions ─────────────────────────────────────────────────────────


def _condition_baseline(
    args: argparse.Namespace, tokens: list[int]
) -> dict[str, Any]:
    cfg = _cfg(
        dim=args.dim, m=args.m, n=args.n, r=args.r,
        phi_compress_enabled=False, seed=args.seed,
    )
    pipeline = LanguagePipeline(cfg)
    # Warm up the field so R stabilizes before we record.
    _run(pipeline, tokens, args.warmup)
    rs = _run(pipeline, tokens, args.steps)
    mean, std = _band(rs)
    return {
        "mode": "baseline",
        "r": int(args.r),
        "phi_compress_enabled": False,
        "R_mean": mean,
        "R_std": std,
        "R_min": float(np.min(rs)),
        "R_max": float(np.max(rs)),
        "trajectory_head": rs[:20],
    }


def _condition_off(
    args: argparse.Namespace, tokens: list[int]
) -> dict[str, Any]:
    """Rebuild-without-transfer: contract to r=4, keep random start."""
    cfg = _cfg(
        dim=args.dim, m=args.m, n=args.n, r=args.r,
        phi_compress_enabled=False, seed=args.seed,
    )
    pipeline = LanguagePipeline(cfg)
    _run(pipeline, tokens, args.warmup)

    # Pre-contract band
    pre_rs = _run(pipeline, tokens, args.steps_pre)
    pre_mean, pre_std = _band(pre_rs)

    # Manual rebuild without transfer (the failure mode the fix addresses).
    from resileos.substrate.oscillator import KuramotoField
    from resileos.core import CoreConfig, ResidualCore

    new_r = contract_rank(pipeline.core.cfg.r, min_rank=4)
    pipeline.core = ResidualCore(
        CoreConfig(m=args.m, n=args.n, r=new_r),
        seed=args.seed,
        non_conservative=True,
    )
    pipeline.field = KuramotoField(
        r=new_r,
        ladder="golden_powers",
        kappa=cfg.oscillator_kappa,
        alpha=cfg.oscillator_alpha,
        dt=cfg.oscillator_dt,
        random_start=True,   # <-- the failure mode
        seed=args.seed,
    )
    pipeline._W_osc = np.ones((new_r, new_r)) - np.eye(new_r)

    post_rs = _run(pipeline, tokens, args.steps_post)
    post_mean, post_std = _band(post_rs)
    recovery = _recovery_steps(post_rs, pre_mean, pre_std, 0)
    return {
        "mode": "off_rebuild_random_start",
        "r_pre": int(args.r),
        "r_post": int(new_r),
        "R_pre_mean": pre_mean,
        "R_pre_std": pre_std,
        "R_post_mean": post_mean,
        "R_post_std": post_std,
        "delta_mean": abs(post_mean - pre_mean),
        "recovery_steps": recovery,
        "trajectory_post_head": post_rs[:20],
    }


def _condition_on(
    args: argparse.Namespace, tokens: list[int]
) -> dict[str, Any]:
    """Actual phi-compress path: transfer θ/ω, fire after warmup."""
    cfg = _cfg(
        dim=args.dim, m=args.m, n=args.n, r=args.r,
        phi_compress_enabled=True,
        phi_compress_warmup=args.warmup,
        phi_compress_min_R=0.0,
        phi_compress_min_rank=4,
        seed=args.seed,
    )
    pipeline = LanguagePipeline(cfg)
    _run(pipeline, tokens, args.warmup)

    # Pre-contract band, warmup already past, compression may fire during
    # these steps. To measure the band before firing we hold the field
    # in the pre-contract state by disabling contraction for this window.
    # Simplest: record R for steps_pre with compress off, then re-enable.
    pipeline.cfg.phi_compress_enabled = False
    pre_rs = _run(pipeline, tokens, args.steps_pre)
    pre_mean, pre_std = _band(pre_rs)

    # Enable compression, run until it fires (or max steps).
    pipeline.cfg.phi_compress_enabled = True
    fire_step = -1
    post_rs: list[float] = []
    compressed = False
    for i in range(args.steps_post):
        window = tokens[(i % 8) : (i % 8) + 8] or tokens[:8]
        pipeline.step(window)
        post_rs.append(float(pipeline._last_R))
        if not compressed and len(pipeline.stats()["compressions"]) > 0:
            compressed = True
            fire_step = i

    post_mean, post_std = _band(post_rs)
    recovery = (
        _recovery_steps(post_rs, pre_mean, pre_std, fire_step)
        if fire_step >= 0 else None
    )
    return {
        "mode": "on_transfer",
        "r_pre": int(args.r),
        "r_post": int(pipeline.core.cfg.r),
        "compressed": bool(compressed),
        "fire_step": int(fire_step),
        "R_pre_mean": pre_mean,
        "R_pre_std": pre_std,
        "R_post_mean": post_mean,
        "R_post_std": post_std,
        "delta_mean": abs(post_mean - pre_mean),
        "recovery_steps": recovery,
        "trajectory_post_head": post_rs[:20],
    }


# ── main ───────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="phi-compress orientation probe")
    ap.add_argument("--dim", type=int, default=512)
    ap.add_argument("--m", type=int, default=22)
    ap.add_argument("--n", type=int, default=23)
    ap.add_argument("--r", type=int, default=8)
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--steps-pre", type=int, default=100)
    ap.add_argument("--steps-post", type=int, default=100)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--out", type=str, default="artifacts/report_phi_compress_probe.json"
    )
    args = ap.parse_args()

    if args.m * args.n != args.dim:
        raise SystemExit(f"m*n ({args.m*args.n}) != dim ({args.dim})")

    # Fixed token stream. The probe is about field state, not language
    # semantics; any deterministic sequence works.
    tokens = list(range(1, 17))

    print(f"phi-compress orientation probe  dim={args.dim} r={args.r}")
    print(f"  warmup={args.warmup}  pre={args.steps_pre}  post={args.steps_post}")

    baseline = _condition_baseline(args, tokens)
    off = _condition_off(args, tokens)
    on = _condition_on(args, tokens)

    # Pass condition per RES-401 §4
    if not on["compressed"]:
        verdict = "not fired: compression did not trigger in the post window"
        passed = False
    elif on["delta_mean"] < 0.05 and (on["recovery_steps"] is not None
                                     and on["recovery_steps"] < 10):
        verdict = "PASS: orientation preserved under contraction"
        passed = True
    elif on["delta_mean"] < 0.05:
        verdict = (
            "PARTIAL: R band preserved but recovery "
            f"{on['recovery_steps']} >= 10 steps"
        )
        passed = False
    else:
        verdict = (
            f"FAIL: R band shifted by {on['delta_mean']:.4f} "
            f"(>= 0.05) after contraction"
        )
        passed = False

    report = {
        "probe": "phi_compress_orientation",
        "config": {
            "dim": args.dim, "m": args.m, "n": args.n,
            "r": args.r, "warmup": args.warmup,
            "steps_pre": args.steps_pre, "steps_post": args.steps_post,
            "seed": args.seed,
        },
        "conditions": {
            "baseline": baseline,
            "off_rebuild_random_start": off,
            "on_transfer": on,
        },
        "pass_condition": {
            "delta_mean_max": 0.05,
            "recovery_steps_max": 10,
        },
        "verdict": verdict,
        "passed": passed,
        "notes": [
            "baseline: no compression, establishes the un-contracted band",
            "off_rebuild_random_start: contract + rebuild with random_start=True",
            "on_transfer: actual _maybe_contract path (θ/ω transfer)",
            "delta_mean = |R_post_mean - R_pre_mean|",
            "recovery_steps = steps after fire until R returns to 2σ band",
            "RES-401 §4: PASS requires delta < 0.05 AND recovery < 10",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print()
    print(f"baseline R:        {baseline['R_mean']:.4f} ± {baseline['R_std']:.4f}")
    print(
        f"off (random):      pre={off['R_pre_mean']:.4f}  "
        f"post={off['R_post_mean']:.4f}  "
        f"delta={off['delta_mean']:.4f}  "
        f"recovery={off['recovery_steps']}"
    )
    print(
        f"on (transfer):     pre={on['R_pre_mean']:.4f}  "
        f"post={on['R_post_mean']:.4f}  "
        f"delta={on['delta_mean']:.4f}  "
        f"recovery={on['recovery_steps']}  "
        f"fire={on['fire_step']}"
    )
    print()
    print(f"verdict: {verdict}")
    print(f"wrote {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
