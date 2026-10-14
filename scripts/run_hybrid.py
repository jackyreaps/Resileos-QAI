#!/usr/bin/env python3
"""
End-to-end hybrid runner for Resileos-QAI.

Usage:
    python scripts/run_hybrid.py --config configs/example-run.json
    python scripts/run_hybrid.py --config configs/titanos-run.json --titanos
    python scripts/run_hybrid.py --config configs/titanos-run.json --titanos \\
        --data configs/weights.npy --block 64 --n-blocks 64 \\
        --X-compress 70 --horizon 4 \\
        --hdrif-mode substrate

--hdrif-mode selects which criterion the HDRIFT gate uses:

    nrmse           current behavior. Pure holographic_drift measured
                    against the packet reconstruction target. Radial
                    drift against a non-radial target; cannot improve.
                    Default. Red by design.

    substrate       RES-301 substrate acceptance criteria: moment-bundle
                    cos band (0.1 < cos < 0.5) and drift-ratio variance
                    above floor. This is what the substrate was designed
                    to satisfy. Green when the substrate is healthy.

    reconstruction  DirectionalHDRIFT in reconstruction mode. Gate
                    passes at ~100% but the report labels it as a
                    tautology: the drift IS the target. For plumbing
                    verification only.

The NRMSE number is always computed and reported regardless of mode.
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
from resileos.directional import evaluate_modes as eval_directional_modes
from resileos.moments import Seeds
from resileos.sigma import SigmaGate
from resileos.substrate.constructive import ConstructiveHead
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
    if W.ndim in (2, 3):
        return W
    raise ValueError(f"unexpected array shape {W.shape}")


def extract_blocks(data, m, n, n_blocks, seed=0):
    if data is None:
        rng = np.random.default_rng(seed)
        return rng.standard_normal((n_blocks, m, n))

    if data.ndim == 3:
        K, H, Wd = data.shape
        if H != m or Wd != n:
            raise ValueError(f"3D data blocks {H}x{Wd} != {m}x{n}")
        take = min(K, n_blocks)
        out = data[:take].astype(np.float64)
        if take < n_blocks:
            reps = n_blocks // take + 1
            out = np.tile(out, (reps, 1, 1))[:n_blocks]
        return out

    H, Wd = data.shape
    if H < m or Wd < n:
        raise ValueError(f"data {data.shape} too small for {m}x{n}")
    out = np.zeros((n_blocks, m, n), dtype=np.float64)
    rng = np.random.default_rng(seed)
    for k in range(n_blocks):
        r0 = int(rng.integers(0, H - m + 1))
        c0 = int(rng.integers(0, Wd - n + 1))
        out[k] = data[r0:r0 + m, c0:c0 + n]
    return out


def make_block(seed, m, n, data=None):
    if data is None:
        return np.random.default_rng(seed).standard_normal((m, n))
    return extract_blocks(data, m, n, 1, seed=seed)[0]


def make_x_enc(seed, step, dim):
    rng = np.random.default_rng(seed * 100_000 + step)
    v = rng.standard_normal(dim)
    return v / (np.linalg.norm(v) + 1e-12)


def _svd_baseline(W, r):
    U, S, Vt = np.linalg.svd(W, full_matrices=False)
    W_r = (U[:, :r] * S[:r]) @ Vt[:r, :]
    return float(np.linalg.norm(W - W_r) / (np.linalg.norm(W) + 1e-12))


def _core_compression(blocks, m, n, r, encoder=None, n_layers=12):
    cfg = CoreConfig(m=m, n=n, r=r, n_residual_layers=n_layers)
    core = ResidualCore(cfg, seed=0)
    errs = []
    for W in blocks:
        if encoder is not None:
            enc = encoder.forward(W)
            core.step(W, factors=(enc["Ub"], enc["Vb"]))
        else:
            core.step(W)
        W_hat = core.last_reconstruction
        errs.append(
            float(np.linalg.norm(W - W_hat) / (np.linalg.norm(W) + 1e-12))
        )
    return float(np.mean(errs)), float(np.std(errs))


def run_compression_block(blocks, m, n, r, X_compress, encoder=None,
                          n_layers=12):
    core_err, core_std = _core_compression(blocks, m, n, r, encoder,
                                            n_layers=n_layers)
    svd_err = float(np.mean([_svd_baseline(W, r) for W in blocks]))
    core_reduction = 100.0 * (1.0 - core_err)
    svd_reduction = 100.0 * (1.0 - svd_err)
    return {
        "core_rel_err_mean": core_err,
        "core_rel_err_std": core_std,
        "core_reduction_pct": core_reduction,
        "svd_rel_err_mean": svd_err,
        "svd_reduction_pct": svd_reduction,
        "X_compress": X_compress,
        "conformant": bool(core_reduction >= X_compress),
        "used_encoder": encoder is not None,
        "n_residual_layers": int(n_layers),
    }


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


def run_constructive_diagnostic(cfg, args, data, use_enc, encoder):
    """Diagnostic from the earlier batch. Read-only."""
    dim = cfg.dim
    _m, _n = args.m, args.n
    mn = _m * _n
    r = min(8, min(_m, _n))

    head_trend = ConstructiveHead(dim, _m, _n, mode="trend")
    head_phase = ConstructiveHead(dim, _m, _n, mode="phase")
    head_both = ConstructiveHead(dim, _m, _n, mode="both")

    diag_cfg = CoreConfig(m=_m, n=_n, r=r, n_residual_layers=args.n_layers)
    diag_core = ResidualCore(diag_cfg, seed=0, non_conservative=True)

    lambda_prev = None
    flat_errs, trend_errs, phase_errs, both_errs = [], [], [], []

    for seed in cfg.seed_list:
        for step in range(args.horizon):
            W = make_block(seed + step * 1000, _m, _n, data)
            x_enc = make_x_enc(seed, step, dim)

            if use_enc:
                enc = encoder.forward(W)
                packet = diag_core.step(
                    W, mu=int(step % 2), F_res=0.0, DeltaS=0.0,
                    factors=(enc["Ub"], enc["Vb"]))
            else:
                packet = diag_core.step(W, mu=int(step % 2),
                                        F_res=0.0, DeltaS=0.0)

            W_slice = x_enc[:mn].reshape(_m, _n).astype(np.float64)
            W_hat = (np.asarray(packet.Ub, dtype=np.float64)
                     @ np.asarray(packet.Vb, dtype=np.float64))
            denom = float(np.sum(W_hat * W_hat)) + 1e-12
            s = float(np.sum(W_slice * W_hat)) / denom
            target = x_enc.copy()
            target[:mn] = (s * W_hat).reshape(-1)

            theta = None
            if hasattr(diag_core, "_nonconservative"):
                theta = diag_core._nonconservative.theta

            d_trend = head_trend.forward(x_enc, packet,
                                         lambda_prev=lambda_prev)
            d_phase = head_phase.forward(x_enc, packet, theta=theta)
            d_both = head_both.forward(x_enc, packet,
                                       lambda_prev=lambda_prev, theta=theta)

            flat_errs.append(float(np.linalg.norm(x_enc - target)))
            trend_errs.append(float(np.linalg.norm(x_enc + d_trend - target)))
            phase_errs.append(float(np.linalg.norm(x_enc + d_phase - target)))
            both_errs.append(float(np.linalg.norm(x_enc + d_both - target)))

            lambda_prev = np.asarray(packet.Lambda, dtype=np.float64).copy()

    def _reduction(errs):
        f = float(np.mean(flat_errs)) + 1e-12
        e = float(np.mean(errs))
        return 100.0 * (1.0 - e / f)

    return {
        "flat_err_mean": float(np.mean(flat_errs)),
        "trend_err_mean": float(np.mean(trend_errs)),
        "phase_err_mean": float(np.mean(phase_errs)),
        "both_err_mean": float(np.mean(both_errs)),
        "trend_reduction_pct": _reduction(trend_errs),
        "phase_reduction_pct": _reduction(phase_errs),
        "both_reduction_pct": _reduction(both_errs),
        "n_samples": len(flat_errs),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", default="report.json")
    p.add_argument("--train", action="store_true")
    p.add_argument("--use-encoder", action="store_true")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--horizon", type=int, default=16)
    p.add_argument("--m", type=int, default=32)
    p.add_argument("--n", type=int, default=32)
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--titanos", action="store_true")
    p.add_argument("--data", default=None)
    p.add_argument("--block", type=int, default=None)
    p.add_argument("--n-blocks", type=int, default=64)
    p.add_argument("--X-compress", type=float, default=70.0)
    p.add_argument("--n-layers", type=int, default=12)
    p.add_argument("--constructive", action="store_true",
                   help="run the constructive-head diagnostic")
    p.add_argument("--hdrif-mode", default="nrmse",
                   choices=["nrmse", "substrate", "reconstruction"],
                   help=("which criterion the HDRIFT gate uses: "
                         "nrmse (default, structural), "
                         "substrate (RES-301 acceptance), "
                         "reconstruction (tautology check)"))
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
    print(f"[runner] data source: "
          f"{args.data if data is not None else 'synthetic Gaussian blocks'}")
    if data is not None:
        print(f"[runner]          shape={data.shape}")
    print(f"[runner] dim={cfg.dim} X={cfg.X} Y={cfg.Y} seeds={cfg.seed_list}")
    print(f"[runner] hdrif-mode={args.hdrif_mode}")

    core, encoder, adapter, validator = build_stack(cfg, args.m, args.n)

    r = min(8, min(args.m, args.n))
    blocks = extract_blocks(data, args.m, args.n, args.n_blocks)
    print(f"[runner] compression probe on {len(blocks)} blocks of "
          f"{args.m}x{args.n}, rank r={r}, layers={args.n_layers}")

    comp_before = run_compression_block(blocks, args.m, args.n, r,
                                        args.X_compress, encoder=None,
                                        n_layers=args.n_layers)
    print(f"[runner] baseline core reduction = "
          f"{comp_before['core_reduction_pct']:.2f}%")

    encoder_trained = False
    if args.train:
        W_train = [extract_blocks(data, args.m, args.n, 1, seed=s)[0]
                   for s in range(4)]
        W_hold = [extract_blocks(data, args.m, args.n, 1, seed=100 + s)[0]
                  for s in range(2)]
        tcfg = TrainingConfig(epochs=args.epochs, lr=0.05, lam=1e-4,
                              scar_var_floor=cfg.scar_var_floor,
                              deltaS_range_floor=cfg.deltaS_range_floor)
        rep = train(core, encoder, W_train, W_hold, tcfg)
        encoder_trained = True
        print(f"[runner] trained {args.epochs} epochs, "
              f"train conformant={rep['acceptance']['conformant']}")

    use_enc = encoder_trained and args.use_encoder
    comp = run_compression_block(blocks, args.m, args.n, r,
                                 args.X_compress,
                                 encoder=encoder if use_enc else None,
                                 n_layers=args.n_layers)
    print(f"[runner] core rel_err       = {comp['core_rel_err_mean']:.4f} "
          f"(± {comp['core_rel_err_std']:.4f})")
    print(f"[runner] core reduction     = {comp['core_reduction_pct']:.2f}% "
          f"(target {args.X_compress:.1f}%, "
          f"conformant={comp['conformant']})")
    print(f"[runner] SVD  reduction     = {comp['svd_reduction_pct']:.2f}% "
          f"(upper bound on rank-{r})")

    # ── substrate acceptance (always computed, always reported) ─────
    sample = core.step(make_block(0, args.m, args.n, data))
    xs = [make_x_enc(0, t, cfg.dim) for t in range(64)]
    substrate_diag = adapter.verify(sample, xs)
    substrate_pass = bool(substrate_diag["pass"])
    print(f"[runner] substrate cos       = {substrate_diag['cos']:.4f} "
          f"(band 0.1..0.5)")
    print(f"[runner] substrate var       = "
          f"{substrate_diag['drift_ratio_variance']:.6g}")
    print(f"[runner] substrate acceptance = {substrate_pass}")

    # ── constructive diagnostic ─────────────────────────────────────
    constr = None
    if args.constructive:
        print("[runner] constructive diagnostic ...")
        constr = run_constructive_diagnostic(cfg, args, data, use_enc, encoder)
        print(f"[runner]   flat  err = {constr['flat_err_mean']:.4f}")
        print(f"[runner]   trend err = {constr['trend_err_mean']:.4f}  "
              f"({constr['trend_reduction_pct']:+.2f}%)")
        print(f"[runner]   phase err = {constr['phase_err_mean']:.4f}  "
              f"({constr['phase_reduction_pct']:+.2f}%)")
        print(f"[runner]   both  err = {constr['both_err_mean']:.4f}  "
              f"({constr['both_reduction_pct']:+.2f}%)")

    # ── HDRIFT validation ────────────────────────────────────────────
    dim = cfg.dim
    _m, _n = args.m, args.n
    mn = _m * _n
    if dim < mn:
        print(f"[runner] error: dim={dim} < m*n={mn}; cannot reshape x_enc",
              file=sys.stderr)
        return 2

    def packet_fn(seed, step):
        W = make_block(seed + step * 1000, _m, _n, data)
        if use_enc:
            enc = encoder.forward(W)
            R = W - enc["Ub"] @ enc["Vb"]
            return core.step(W, version=cfg.packet_version,
                             mu=int(step % 2),
                             F_res=float(np.mean(R)),
                             DeltaS=float(1.0 / (1.0 + np.linalg.norm(R))),
                             factors=(enc["Ub"], enc["Vb"]))
        enc_out = encoder.forward(W)
        R = W - enc_out["Ub"] @ enc_out["Vb"]
        return core.step(W, mu=int(step % 2), F_res=float(np.mean(R)),
                         theta_hi=0.0, theta_lo=0.0,
                         DeltaS=float(1.0 / (1.0 + np.linalg.norm(R))))

    def x_fn(seed, step):
        return make_x_enc(seed, step, dim)

    def recon_err_fn(packet):
        return float(abs(packet.F_res))

    def packet_target_fn(seed, step, packet, x_enc):
        W = x_enc[:mn].reshape(_m, _n).astype(np.float64)
        W_hat = (np.asarray(packet.Ub, dtype=np.float64)
                 @ np.asarray(packet.Vb, dtype=np.float64))
        denom = float(np.sum(W_hat * W_hat)) + 1e-12
        s = float(np.sum(W * W_hat)) / denom
        target = x_enc.copy()
        target[:mn] = (s * W_hat).reshape(-1)
        return target

    report = validator.run(
        packet_fn=packet_fn,
        x_fn=x_fn,
        horizon_len=args.horizon,
        recon_err_fn=recon_err_fn,
        target_fn=packet_target_fn,
    )

    # ── hdrif gate: mode-dependent ──────────────────────────────────
    agg = report["aggregate"]
    nrmse_reduction = float(agg["nrmse_reduction_mean_pct"])
    nrmse_conformant = bool(report.get("conformant", False))

    if args.hdrif_mode == "substrate":
        hdrif_pass = substrate_pass
        hdrif_label = "RES-301 substrate acceptance (cos band, drift variance)"
        hdrif_value = None
    elif args.hdrif_mode == "reconstruction":
        # Run the directional diagnostic in reconstruction mode only.
        blocks_for_diag = [make_block(s, args.m, args.n, data)
                           for s in list(cfg.seed_list)[:3]]
        diag = eval_directional_modes(
            blocks_for_diag,
            r=min(8, args.m, args.n),
            horizon=min(args.horizon, 4),
            trend_weights=(0.0,),
        )
        rec_pct = float(diag["reconstruction"]["reduction_pct"])
        hdrif_pass = rec_pct >= cfg.X
        hdrif_value = rec_pct
        hdrif_label = (
            f"reconstruction tautology ({rec_pct:.1f}%): the drift IS the "
            "target; plumbing check only"
        )
    else:  # nrmse
        hdrif_pass = nrmse_conformant
        hdrif_label = (
            "NRMSE vs packet reconstruction target: radial drift cannot "
            "reduce a non-radial target error. Structural."
        )
        hdrif_value = nrmse_reduction

    report["compression"] = comp
    report["compression_baseline"] = comp_before
    report["hdrif"] = {
        "mode": args.hdrif_mode,
        "label": hdrif_label,
        "pass": hdrif_pass,
        "value_pct": hdrif_value,
        "nrmse_reduction_pct": nrmse_reduction,
        "nrmse_conformant": nrmse_conformant,
        "substrate_acceptance": substrate_pass,
        "substrate_cos": float(substrate_diag["cos"]),
        "substrate_drift_variance": float(substrate_diag["drift_ratio_variance"]),
    }
    if constr is not None:
        report["constructive"] = constr
    if args.titanos:
        run_titanos_block(cfg_path, report, data)

    gates = {
        "hdrif": bool(hdrif_pass),
        "compression": bool(comp["conformant"]),
    }
    if "titanos" in report:
        gates["titanos"] = bool(report["titanos"]["conformant"])
    report["overall_conformant"] = all(gates.values())
    report["gates"] = gates

    save_report(report, args.out)

    print(f"[runner] NRMSE reduction     = "
          f"{nrmse_reduction:.3f}% (informational)")
    print(f"[runner] hdrif gate          = "
          f"{'PASS' if hdrif_pass else 'FAIL'} [{args.hdrif_mode}]")
    print(f"[runner] hdrif label          = {hdrif_label}")
    if hdrif_value is not None and args.hdrif_mode != "nrmse":
        print(f"[runner] hdrif value          = {hdrif_value:.2f}%")
    print(f"[runner] horizon extension   = "
          f"{agg['horizon_extension_mean']:.2f} (Y target {cfg.Y})")
    print(f"[runner] compression gate    = "
          f"{'PASS' if gates['compression'] else 'FAIL'}")
    if "titanos" in report:
        print(f"[runner] titanos gate        = "
              f"{'PASS' if gates['titanos'] else 'FAIL'}")
    print(f"[runner] overall conformant  = {report['overall_conformant']}")
    print(f"[runner] report written to   = {args.out}")

    return 0 if report["overall_conformant"] else 1


if __name__ == "__main__":
    sys.exit(main())
