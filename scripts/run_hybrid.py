#!/usr/bin/env python3
"""
End-to-end hybrid runner for Resileos-QAI.

Usage:
    python scripts/run_hybrid.py --config configs/example-run.json
    python scripts/run_hybrid.py --config configs/titanos-run.json --titanos
    python scripts/run_hybrid.py --config configs/titanos-run.json --titanos \
        --data weights.npy --block 64
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from resileos.abstention import AbstentionThresholds
from resileos.adapter import HDRIFTAdapter
from resileos.core import CoreConfig, ResidualCore
from resileos.moments import Seeds
from resileos.sigma import SigmaGate
from resileos.training import FrontEndEncoder, TrainingConfig, train
from resileos.validation import HybridValidator, RunConfig, save_report


def _filter_for(cls, raw):
    valid = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in raw.items() if k in valid}


def load_run_config(path):
    raw = json.loads(path.read_text())
    if "seeds" in raw:
        raw["seeds"] = Seeds(**raw["seeds"])
    if "seed_list" in raw:
        raw["seed_list"] = tuple(raw["seed_list"])
    return RunConfig(**_filter_for(RunConfig, raw))


_DATA_CACHE = {}


def load_data(path, m, n):
    if path is None:
        return None
    key = str(path)
    if key not in _DATA_CACHE:
        _DATA_CACHE[key] = np.load(str(path))
    W = _DATA_CACHE[key]
    if W.ndim != 2:
        raise ValueError(f"expected 2D array, got shape {W.shape}")
    return W


def make_block(seed, m, n, data=None):
    if data is None:
        return np.random.default_rng(seed).standard_normal((m, n))
    H, Wd = data.shape
    if H < m or Wd < n:
        raise ValueError(f"data {data.shape} too small for {m}x{n}")
    rows = (H - m) // max(1, (seed % 32 + 1))
    cols = (Wd - n) // max(1, (seed % 16 + 1))
    r0 = min(rows, max(0, H - m))
    c0 = min(cols, max(0, Wd - n))
    return data[r0:r0 + m, c0:c0 + n].astype(np.float64)


def make_x_enc(seed, step, dim):
    rng = np.random.default_rng(seed * 100_000 + step)
    v = rng.standard_normal(dim)
    return v / (np.linalg.norm(v) + 1e-12)


def build_stack(cfg, m, n):
    r = min(8, min(m, n))
    core = ResidualCore(CoreConfig(m=m, n=n, r=r), seed=0)
    encoder = FrontEndEncoder(m=m, n=n, r=r, seed=0)
    adapter = HDRIFTAdapter(dim=cfg.dim, seeds=cfg.seeds,
                            drift_ratio_floor=cfg.drift_ratio_floor)
    thresholds = AbstentionThresholds(E_sat=cfg.E_sat, tau_sat=cfg.tau_sat,
                                      tau_low=cfg.tau_low)
    gate = SigmaGate(E_sigma=cfg.E_sigma, k=cfg.sigma1_k)
    validator = HybridValidator(cfg, adapter, thresholds, sigma_gate=gate)
    return core, encoder, adapter, validator


def _is_hit(got, expected):
    """expected can be str or list of str. Hit if got matches any."""
    if isinstance(expected, list):
        return got in expected
    return got == expected


def run_titanos_block(cfg_path, report, data=None):
    try:
        from titanos import Titanos, TitanosConfig
    except ImportError:
        print("[runner] titanos.py not importable, skipping --titanos")
        return

    corpus_path = ROOT / "configs" / "titanos-facts.json"
    if not corpus_path.exists():
        print(f"[runner] corpus missing: {corpus_path}, skipping --titanos")
        return

    try:
        raw_cfg = json.loads(cfg_path.read_text())
        tcfg = TitanosConfig(**_filter_for(TitanosConfig, raw_cfg))
    except Exception as e:
        print(f"[runner] TitanosConfig construction failed: {e}")
        return

    titan = Titanos(tcfg)
    raw = json.loads(corpus_path.read_text())
    for s, r, o in raw["facts"]:
        titan.learn(s, r, o)

    correct, abstained = 0, 0
    modes = Counter()
    details = []

    for q in raw["queries"]:
        ans = (titan.ask_inverse(q["subject"], q["relation"])
               if q["inverse"] else titan.ask(q["subject"], q["relation"]))
        modes[ans.mode] += 1
        hit = ans.status == "ACCEPTED" and _is_hit(ans.value, q["expected"])
        if ans.status == "ABSTAINED":
            abstained += 1
        if hit:
            correct += 1
        details.append({
            "subject": q["subject"], "relation": q["relation"],
            "inverse": q["inverse"], "expected": q["expected"],
            "got": ans.value, "status": ans.status,
            "confidence": float(ans.confidence), "hit": hit,
        })

    total = len(raw["queries"])
    accuracy = 100.0 * correct / max(total, 1)

    report["titanos"] = {
        "accuracy_pct": accuracy,
        "X_target": tcfg.X,
        "conformant": bool(accuracy >= tcfg.X),
        "queries_total": total,
        "queries_correct": correct,
        "abstentions": abstained,
        "modes": dict(modes),
        "stats": titan.stats(),
        "details": details,
    }
    print(f"[runner] titanos accuracy   = {accuracy:.2f}% "
          f"({correct}/{total}, target {tcfg.X:.1f}%, "
          f"conformant={report['titanos']['conformant']})")
    for d in details:
        if not d["hit"]:
            print(f"[runner]   miss: {d['subject']} --{d['relation']}--> "
                  f"expected {d['expected']}, got {d['got']} "
                  f"({d['status']}, conf {d['confidence']:.4f})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", default="report.json")
    p.add_argument("--train", action="store_true")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--horizon", type=int, default=16)
    p.add_argument("--m", type=int, default=32)
    p.add_argument("--n", type=int, default=32)
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--titanos", action="store_true")
    p.add_argument("--data", default=None)
    p.add_argument("--block", type=int, default=None)
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"error: config not found: {cfg_path}", file=sys.stderr)
        return 2

    if args.block is not None:
        args.m = args.n = args.block

    cfg = load_run_config(cfg_path)
    cfg.assert_declared()

    data = load_data(Path(args.data), args.m, args.n) if args.data else None
    if data is not None:
        print(f"[runner] data source: {args.data}  shape={data.shape}")
    else:
        print("[runner] data source: synthetic Gaussian blocks")

    print(f"[runner] dim={cfg.dim} X={cfg.X} Y={cfg.Y} seeds={cfg.seed_list}")

    core, encoder, adapter, validator = build_stack(cfg, args.m, args.n)

    if args.train:
        W_train = [make_block(s, args.m, args.n, data) for s in range(4)]
        W_hold = [make_block(100 + s, args.m, args.n, data) for s in range(2)]
        tcfg = TrainingConfig(epochs=args.epochs, lr=0.05, lam=1e-4,
                              scar_var_floor=cfg.scar_var_floor,
                              deltaS_range_floor=cfg.deltaS_range_floor)
        rep = train(core, encoder, W_train, W_hold, tcfg)
        print(f"[runner] train conformant = {rep['acceptance']['conformant']}")

    if not args.no_verify:
        sample = core.step(make_block(0, args.m, args.n, data))
        xs = [make_x_enc(0, t, cfg.dim) for t in range(64)]
        diag = adapter.verify(sample, xs)
        print(f"[runner] adapter cos={diag['cos']:.4f} "
              f"var={diag['drift_ratio_variance']:.6g} pass={diag['pass']}")

    def packet_fn(seed, step):
        W = make_block(seed + step * 1000, args.m, args.n, data)
        enc_out = encoder.forward(W)
        Ub, Vb = enc_out["Ub"], enc_out["Vb"]
        R = W - Ub @ Vb
        return core.step(W=W, mu=int(step % 2), F_res=float(np.mean(R)),
                         theta_hi=0.0, theta_lo=0.0,
                         DeltaS=float(1.0 / (1.0 + np.linalg.norm(R))))

    def x_fn(seed, step):
        return make_x_enc(seed, step, cfg.dim)

    def recon_err_fn(packet):
        return float(abs(packet.F_res))

    report = validator.run(packet_fn=packet_fn, x_fn=x_fn,
                           horizon_len=args.horizon, recon_err_fn=recon_err_fn)

    if args.titanos:
        run_titanos_block(cfg_path, report, data)

    save_report(report, args.out)

    agg = report["aggregate"]
    print(f"[runner] NRMSE reduction     = {agg['nrmse_reduction_mean_pct']:.3f}%")
    print(f"[runner] horizon extension   = {agg['horizon_extension_mean']:.2f}")
    print(f"[runner] conformant          = {report['conformant']}")
    if "titanos" in report:
        print(f"[runner] titanos conformant  = {report['titanos']['conformant']}")
    print(f"[runner] report written to   = {args.out}")

    return 0 if report["conformant"] else 1


if __name__ == "__main__":
    sys.exit(main())
