#!/usr/bin/env python3
"""Efficiency ablation (Hardened Roadmap v1.0.x, item 1.1 — BLOCKING).

Measures whether framework-native training is more sample-efficient than
plain next-token training, at toy scale. Nothing in v2.0.0 proceeds until
this returns a number.

Same decoder, same carrier, same task. Two modes:

    nll         loss = cross_entropy
    framework   loss = cross_entropy
                       + lambda_R   * recovery  (packet phase, per-channel)
                       + lambda_coh * coherence (channel diversity)
                       + lambda_res * residue   (residue-history coupling)

Three k factors, reported separately. They are not interchangeable:

    k_steps      = steps_nll / steps_framework
                   Sample efficiency. Reliable at toy scale.

    k_flops_est  = (steps_nll * flops_per_step_nll)
                 / (steps_framework * flops_per_step_framework)
                   Compute efficiency, analytic estimate. Accounts for
                   the framework extras (recovery, coherence, residue).
                   Does NOT account for production data generation; enter
                   that separately as D in the roadmap equation.

    k_wall_toy   = wall_nll / wall_framework
                   Wall-clock at toy scale. UNRELIABLE: Python interpreter
                   overhead dominates at this size, so this number trends
                   toward 1.0 regardless of algorithmic cost. Reported for
                   completeness only. Do not feed it into a compute
                   projection.

The roadmap equation uses k_flops_est:

    Total compute = (1.2e24 * (1 + D)) / k_flops_est

Target accuracy is defined before the run, not after:

    target_nll = baseline_nll - target_delta

where baseline_nll is the no-modulation decoder on the held-out set. A
mode that does not reach target within budget contributes k = inf and
the verdict is "not reached". The k <= 1 branch is a first-class outcome,
not an error.

Usage:
    PYTHONPATH=src python scripts/run_efficiency_ablation.py
    PYTHONPATH=src python scripts/run_efficiency_ablation.py --target-delta 0.10
    PYTHONPATH=src python scripts/run_efficiency_ablation.py --steps 3000 --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
for cand in (ROOT / "src", Path.cwd() / "src"):
    if (cand / "resileos").exists():
        sys.path.insert(0, str(cand))
        break

try:
    from resileos.carrier import SubstrateCarrier
    _SUBSTRATE_PRESENT = True
except Exception:
    SubstrateCarrier = None  # type: ignore
    _SUBSTRATE_PRESENT = False


# ── synthetic RES-201 packet with topic structure ───────────────────
def make_packet(
    m: int,
    n: int,
    r: int,
    rng: np.random.Generator,
    topic_id: Optional[int] = None,
    n_topics: int = 4,
) -> dict:
    Ub = rng.standard_normal((m, r))
    Vb = rng.standard_normal((r, n))
    Lam = np.eye(r) + 0.05 * rng.standard_normal((r, r))
    lat = rng.standard_normal(r)
    mu = float(rng.standard_normal())
    if topic_id is not None and n_topics > 0:
        lat[topic_id % r] += 3.0
        mu = (topic_id / max(n_topics - 1, 1)) * 2.0 - 1.0
    return {
        "Ub": Ub,
        "Vb": Vb,
        "Lambda": Lam,
        "row_s_k": rng.standard_normal(m),
        "col_s_k": rng.standard_normal(n),
        "lat_s_k": lat,
        "mu": mu,
        "DeltaS": float(abs(rng.standard_normal()) * 0.1),
        "F_res": float(abs(rng.standard_normal()) * 0.1),
        "volume": float(1.0 + 0.01 * rng.standard_normal()),
        "volume_ok": True,
        "rank": float(r),
    }


def batch_tokens(
    vocab: int,
    batch: int,
    seq: int,
    device: torch.device,
    topic_id: Optional[int] = None,
    n_topics: int = 4,
) -> torch.Tensor:
    if topic_id is None or n_topics <= 1:
        return torch.randint(0, vocab, (batch, seq), device=device)
    region = max(vocab // n_topics, 1)
    lo = (topic_id % n_topics) * region
    hi = min(lo + region, vocab)
    return torch.randint(lo, hi, (batch, seq), device=device)


def _packet_feature_vector(packet: dict) -> torch.Tensor:
    Ub = np.asarray(packet["Ub"]).ravel()
    Vb = np.asarray(packet["Vb"]).ravel()
    Lam = np.asarray(packet["Lambda"]).ravel()
    scalars = np.asarray([
        float(np.mean(packet.get("row_s_k", [0.0]))),
        float(np.mean(packet.get("col_s_k", [0.0]))),
        float(np.mean(packet["lat_s_k"])),
        packet["mu"],
        packet["DeltaS"],
        packet["F_res"],
        float(np.log10(abs(packet["volume"]) + 1e-300)),
        1.0 if packet["volume_ok"] else 0.0,
        float(packet["rank"]),
    ], dtype=np.float64)
    return torch.from_numpy(np.concatenate([Ub, Vb, Lam, scalars])).float()


# ── frozen decoder ──────────────────────────────────────────────────
class TinyFrozenDecoder(nn.Module):
    def __init__(self, vocab: int, d_model: int, n_heads: int = 4, seed: int = 0):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        self.embed = nn.Embedding(vocab, d_model)
        self.block = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=4 * d_model,
            batch_first=True, activation="gelu",
        )
        self.lm_head = nn.Linear(d_model, vocab, bias=False)
        for p in self.parameters():
            if p.dim() >= 2:
                nn.init.xavier_uniform_(p, generator=g)
            else:
                nn.init.zeros_(p)
        for p in self.parameters():
            p.requires_grad_(False)

    def forward(self, input_ids, emb_bias=None, logit_bias=None):
        x = self.embed(input_ids)
        if emb_bias is not None:
            x = x + (emb_bias.view(1, 1, -1) if emb_bias.dim() == 1 else emb_bias)
        x = self.block(x)
        logits = self.lm_head(x)
        if logit_bias is not None:
            logits = logits + (logit_bias.view(1, 1, -1) if logit_bias.dim() == 1 else logit_bias)
        return logits

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


# ── carrier (emb + logit heads, 8 channels) ─────────────────────────
class SectorCarrier(nn.Module):
    def __init__(self, m, n, r, d_model, vocab, n_channels=8, hidden_dim=128, seed=0):
        super().__init__()
        self.n_channels = n_channels
        self.d_model = d_model
        self.vocab = vocab
        try:
            if not _SUBSTRATE_PRESENT:
                raise ImportError
            self.inner_emb = SubstrateCarrier(
                m=m, n=n, r=r,
                output_shape=(n_channels, d_model),
                hidden_dim=hidden_dim, n_layers=2, seed=seed,
                zero_init_output=True,
            )
            self.inner_logit = SubstrateCarrier(
                m=m, n=n, r=r,
                output_shape=(n_channels, vocab),
                hidden_dim=hidden_dim, n_layers=2, seed=seed + 1,
                zero_init_output=True,
            )
            self._fallback = False
        except Exception:
            self._fallback = True
            feat = m * r + r * n + r * r + 9
            self.inner_emb = nn.Sequential(
                nn.Linear(feat, hidden_dim), nn.GELU(),
                nn.Linear(hidden_dim, hidden_dim), nn.GELU(),
                nn.Linear(hidden_dim, n_channels * d_model),
            )
            nn.init.zeros_(self.inner_emb[-1].weight)
            nn.init.zeros_(self.inner_emb[-1].bias)
            self.inner_logit = nn.Sequential(
                nn.Linear(feat, hidden_dim), nn.GELU(),
                nn.Linear(hidden_dim, hidden_dim), nn.GELU(),
                nn.Linear(hidden_dim, n_channels * vocab),
            )
            nn.init.zeros_(self.inner_logit[-1].weight)
            nn.init.zeros_(self.inner_logit[-1].bias)
        self.bias_scale_emb = nn.Parameter(torch.ones(()))
        self.bias_scale_logit = nn.Parameter(torch.ones(()))

    def forward(self, packet):
        if self._fallback:
            f = _packet_feature_vector(packet)
            ch_emb = self.inner_emb(f).view(self.n_channels, self.d_model)
            ch_logit = self.inner_logit(f).view(self.n_channels, self.vocab)
        else:
            ch_emb = self.inner_emb(packet)
            ch_logit = self.inner_logit(packet)
        emb_bias = ch_emb.mean(0) * self.bias_scale_emb
        logit_bias = ch_logit.mean(0) * self.bias_scale_logit
        return ch_emb, emb_bias, logit_bias

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


# ── framework losses ────────────────────────────────────────────────
def make_projection(r, n_channels, d_model, seed):
    g = np.random.default_rng(seed)
    proj = g.standard_normal((r, n_channels, d_model))
    proj /= (np.linalg.norm(proj, axis=0, keepdims=True) + 1e-12)
    return torch.from_numpy(proj).float()


def packet_reference(pkt, proj, device):
    lat = torch.from_numpy(np.asarray(pkt["lat_s_k"])).float().to(device)
    ref = torch.einsum("r,rsd->sd", lat, proj.to(device))
    return F.normalize(ref, dim=-1)


def recovery_loss(channels, ref):
    return (1.0 - (F.normalize(channels, dim=-1) * F.normalize(ref, dim=-1)).sum(-1)).mean()


def coherence_loss(ch_emb):
    """Penalise collapsed channels. 0 = orthogonal, 1 = identical."""
    x = F.normalize(ch_emb, dim=-1)
    gram = x @ x.T
    n = ch_emb.shape[0]
    if n < 2:
        return ch_emb.new_zeros(())
    off = (gram.sum() - torch.diagonal(gram).sum()) / (n * (n - 1))
    return off.abs()


def residue_vector(pkt, r):
    return torch.from_numpy(np.concatenate([
        np.asarray(pkt["lat_s_k"], dtype=np.float64),
        [pkt["mu"], pkt["DeltaS"], pkt["F_res"],
         float(np.log10(abs(pkt["volume"]) + 1e-300)),
         float(pkt["rank"])],
    ])).float()


def residue_loss(emb_bias, residue_ema, d_model):
    if residue_ema.numel() < d_model:
        reps = (d_model // residue_ema.numel()) + 1
        target = residue_ema.repeat(reps)[:d_model]
    else:
        target = residue_ema[:d_model]
    target = F.normalize(target.view(1, -1), dim=-1)
    return 1.0 - F.cosine_similarity(emb_bias.view(1, -1), target).mean()


# ── evaluation ──────────────────────────────────────────────────────
@torch.no_grad()
def eval_nll(decoder, carrier, cfg, device, rng, mode="topic", batches=10):
    decoder.eval()
    if carrier is not None:
        carrier.eval()
    total, n_tok = 0.0, 0
    for b in range(batches):
        topic = b % cfg["n_topics"]
        ids = batch_tokens(
            cfg["vocab"], cfg["batch"], cfg["seq"], device,
            topic_id=topic, n_topics=cfg["n_topics"],
        )
        if mode == "none":
            emb_bias, logit_bias = None, None
        else:
            pkt = make_packet(
                cfg["m"], cfg["n"], cfg["r"], rng,
                topic_id=topic, n_topics=cfg["n_topics"],
            )
            _, emb_bias, logit_bias = carrier(pkt)
        inp, tgt = ids[:, :-1], ids[:, 1:]
        logits = decoder(inp, emb_bias=emb_bias, logit_bias=logit_bias)
        loss = F.cross_entropy(logits.reshape(-1, cfg["vocab"]), tgt.reshape(-1))
        total += float(loss) * tgt.numel()
        n_tok += tgt.numel()
    if carrier is not None:
        carrier.train()
    return total / max(n_tok, 1)


# ── one training mode ───────────────────────────────────────────────
def train_mode(mode, decoder, carrier, proj, cfg, device, rng, rng_eval):
    opt = torch.optim.AdamW(carrier.parameters(), lr=cfg["lr"])
    residue_dim = cfg["r"] + 5
    residue_ema = torch.zeros(residue_dim, device=device)
    costs = {k: 0.0 for k in (
        "data_gen", "carrier_fwd", "decoder_fwd", "aux_loss", "opt_step",
    )}
    steps_to_target = None
    trace = []
    t_start = time.perf_counter()
    decoder.eval()
    carrier.train()
    for step in range(1, cfg["max_steps"] + 1):
        topic = int(rng.integers(0, cfg["n_topics"]))
        t0 = time.perf_counter()
        pkt = make_packet(
            cfg["m"], cfg["n"], cfg["r"], rng,
            topic_id=topic, n_topics=cfg["n_topics"],
        )
        ids = batch_tokens(
            cfg["vocab"], cfg["batch"], cfg["seq"], device,
            topic_id=topic, n_topics=cfg["n_topics"],
        )
        costs["data_gen"] += time.perf_counter() - t0
        inp, tgt = ids[:, :-1], ids[:, 1:]
        t1 = time.perf_counter()
        ch_emb, emb_bias, logit_bias = carrier(pkt)
        costs["carrier_fwd"] += time.perf_counter() - t1
        t2 = time.perf_counter()
        logits = decoder(inp, emb_bias=emb_bias, logit_bias=logit_bias)
        nll = F.cross_entropy(logits.reshape(-1, cfg["vocab"]), tgt.reshape(-1))
        costs["decoder_fwd"] += time.perf_counter() - t2
        t3 = time.perf_counter()
        loss = nll
        aux = {}
        if mode == "framework":
            ref = packet_reference(pkt, proj, device)
            r_loss = recovery_loss(
                ch_emb + cfg["perturb_eps"] * torch.randn_like(ch_emb),
                ref,
            )
            c_loss = coherence_loss(ch_emb)
            res_loss = residue_loss(emb_bias, residue_ema, cfg["d_model"])
            loss = (
                nll
                + cfg["lambda_R"] * r_loss
                + cfg["lambda_coh"] * c_loss
                + cfg["lambda_res"] * res_loss
            )
            aux = {
                "recovery": float(r_loss.detach()),
                "coherence": float(c_loss.detach()),
                "residue": float(res_loss.detach()),
            }
        costs["aux_loss"] += time.perf_counter() - t3
        t4 = time.perf_counter()
        opt.zero_grad()
        loss.backward()
        opt.step()
        costs["opt_step"] += time.perf_counter() - t4
        # residue EMA after the step, outside the graph
        with torch.no_grad():
            rv = residue_vector(pkt, cfg["r"]).to(device)
            residue_ema.mul_(cfg["residue_beta"]).add_(
                (1 - cfg["residue_beta"]) * rv
            )
        if step % cfg["eval_every"] == 0 or step == 1:
            held = eval_nll(decoder, carrier, cfg, device, rng_eval, mode="topic")
            rec = {
                "step": step,
                "held_nll": held,
                "train_nll": float(nll.detach()),
                **aux,
            }
            trace.append(rec)
            if steps_to_target is None and held <= cfg["target_nll"]:
                steps_to_target = step
                break
    wall = time.perf_counter() - t_start
    total_steps = trace[-1]["step"] if trace else 0
    # analytic FLOP estimate per step
    n_tok = cfg["batch"] * (cfg["seq"] - 1)
    p_dec = decoder.param_count()
    p_car = carrier.param_count()
    flops_decoder = 6.0 * p_dec * n_tok
    flops_carrier = 6.0 * p_car
    flops_bias_add = n_tok * (cfg["d_model"] + cfg["vocab"])
    flops_base = flops_decoder + flops_carrier + flops_bias_add
    flops_aux = 0.0
    if mode == "framework":
        flops_aux = (
            2.0 * (cfg["r"] * cfg["n_channels"] * cfg["d_model"])  # recovery
            + 2.0 * (cfg["n_channels"] ** 2 * cfg["d_model"])      # coherence
            + 2.0 * cfg["d_model"]                                 # residue
            + 2.0 * (cfg["m"] * cfg["r"] + cfg["r"] * cfg["n"])    # data gen proxy
        )
    flops_per_step = flops_base + flops_aux
    return {
        "mode": mode,
        "steps_to_target": steps_to_target,
        "steps_run": total_steps,
        "wall_seconds": wall,
        "wall_per_step": wall / max(total_steps, 1),
        "flops_per_step_est": flops_per_step,
        "total_flops_est": flops_per_step * total_steps,
        "cost_breakdown_seconds": costs,
        "final_held_nll": trace[-1]["held_nll"] if trace else None,
        "trace": trace,
    }


# ── main ────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=2000,
                    help="max steps per mode")
    ap.add_argument("--eval-every", type=int, default=25)
    ap.add_argument("--target-delta", type=float, default=0.05,
                    help="target_nll = baseline_nll - target_delta")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--m", type=int, default=16)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--r", type=int, default=8)
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--vocab", type=int, default=128)
    ap.add_argument("--seq", type=int, default=16)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--channels", type=int, default=8)
    ap.add_argument("--n-topics", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lambda-R", type=float, default=0.1)
    ap.add_argument("--lambda-coh", type=float, default=0.05)
    ap.add_argument("--lambda-res", type=float, default=0.05)
    ap.add_argument("--perturb-eps", type=float, default=0.05)
    ap.add_argument("--residue-beta", type=float, default=0.95)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    if args.n_topics > args.r:
        raise SystemExit(f"--n-topics {args.n_topics} exceeds --r {args.r}")
    if args.target_delta <= 0:
        raise SystemExit("--target-delta must be > 0")

    torch.manual_seed(args.seed)
    device = torch.device("cpu")
    rng_eval = np.random.default_rng(args.seed + 10_000)

    cfg = {
        "m": args.m,
        "n": args.n,
        "r": args.r,
        "d_model": args.d_model,
        "vocab": args.vocab,
        "seq": args.seq,
        "batch": args.batch,
        "channels": args.channels,
        "n_topics": args.n_topics,
        "lr": args.lr,
        "lambda_R": args.lambda_R,
        "lambda_coh": args.lambda_coh,
        "lambda_res": args.lambda_res,
        "perturb_eps": args.perturb_eps,
        "residue_beta": args.residue_beta,
        "max_steps": args.steps,
        "eval_every": args.eval_every,
        "target_nll": 0.0,  # filled after baseline
        "n_channels": args.channels,
    }

    decoder = TinyFrozenDecoder(
        args.vocab, args.d_model, seed=args.seed,
    ).to(device)
    proj = make_projection(
        args.r, args.channels, args.d_model, args.seed,
    ).to(device)

    # 1. baseline: no modulation at all
    baseline_nll = eval_nll(decoder, None, cfg, device, rng_eval, mode="none")
    cfg["target_nll"] = baseline_nll - args.target_delta
    print(f"baseline (no modulation) held-out NLL: {baseline_nll:.4f}")
    print(f"target NLL: {cfg['target_nll']:.4f} "
          f"(delta {args.target_delta})")
    print()

    results = {}
    for mode in ("nll", "framework"):
        torch.manual_seed(args.seed)  # identical carrier init
        rng = np.random.default_rng(args.seed)
        carrier = SectorCarrier(
            args.m, args.n, args.r, args.d_model, args.vocab,
            n_channels=args.channels, seed=args.seed,
        ).to(device)
        print(f"training mode={mode} ...")
        res = train_mode(mode, decoder, carrier, proj, cfg, device, rng, rng_eval)
        results[mode] = res
        print(
            f"  steps to target: {res['steps_to_target']} "
            f"(ran {res['steps_run']}) "
            f"wall={res['wall_seconds']:.2f}s "
            f"final_held_nll={res['final_held_nll']}"
        )
    print()

    s_nll = results["nll"]["steps_to_target"]
    s_fw = results["framework"]["steps_to_target"]
    f_nll = results["nll"]["total_flops_est"]
    f_fw = results["framework"]["total_flops_est"]
    w_nll = results["nll"]["wall_seconds"]
    w_fw = results["framework"]["wall_seconds"]

    if s_nll is None or s_fw is None:
        verdict = "not reached"
        k_steps = k_flops = k_wall = None
    else:
        k_steps = s_nll / s_fw if s_fw > 0 else float("inf")
        k_flops = f_nll / f_fw if f_fw > 0 else float("inf")
        k_wall = w_nll / w_fw if w_fw > 0 else float("inf")
        if k_flops >= 3.0:
            verdict = "viable: framework-native is materially more efficient"
        elif k_flops > 1.0:
            verdict = "marginal: savings do not justify framework complexity"
        else:
            verdict = (
                "falsified: framework-native is not more efficient "
                "per unit compute; revert to MoE-only"
            )

    report = {
        "ablation": "efficiency_k",
        "substrate_carrier_present": _SUBSTRATE_PRESENT,
        "seed": args.seed,
        "config": cfg,
        "baseline_nll_no_modulation": baseline_nll,
        "modes": results,
        "k_steps": k_steps,
        "k_flops_est": k_flops,
        "k_wall_toy_unreliable": k_wall,
        "verdict": verdict,
        "notes": [
            "k_steps is reliable at toy scale.",
            "k_flops_est is the number for the roadmap scaling equation.",
            "k_wall_toy is Python-bound and trends to 1.0; do not use it.",
            "Production data generation cost D is NOT included in "
            "k_flops_est. Measure it separately and apply "
            "Total = (1.2e24 * (1 + D)) / k_flops_est.",
            "A null result (k <= 1) is a valid outcome and closes the "
            "framework-native objective as a scaling lever.",
        ],
    }
    out = (
        Path(args.out) if args.out
        else (ROOT / "artifacts" / "report_efficiency_ablation.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print("=" * 62)
    print(f"k_steps (sample efficiency): {k_steps}")
    print(f"k_flops_est (compute efficiency): {k_flops}")
    print(f"k_wall_toy (unreliable, Python): {k_wall}")
    print(f"verdict: {verdict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
