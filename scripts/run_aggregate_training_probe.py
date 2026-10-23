#!/usr/bin/env python3
"""Aggregate training probe (Path B).

Does the aggregate (R_shared + upper-tri M + per-engine F_res) from a
coupled EngineGroup reduce object-token NLL on a frozen pretrained
decoder, compared to the uncoupled (κ=0) control?

Design locked by RES-319 §5:
    Input:       aggregate (7-dim for N=3), NOT per-engine lat_s_k
    Ablation:    κ=0 vs κ=2, matched input dimension
    Decoder:     pretrained frozen (Qwen2.5-0.5B or TinyLlama-1.1B)
    Surface:     logit bias (primary)
    Task:        relational on configs/titanos-facts.json
    Loss:        cross-entropy on object token positions only
    Comparison:  baseline | κ=0 carrier | κ=2 carrier

The load-bearing number is `improvement_kappa = nll_k0 - nll_k2`.
Positive means coupling helps. Zero means the aggregate does not carry
task signal beyond what the uncoupled baseline already provides.

Usage:
    python scripts/run_aggregate_training_probe.py \
        --decoder Qwen/Qwen2.5-0.5B --n-steps 500

    python scripts/run_aggregate_training_probe.py \
        --decoder TinyLlama/TinyLlama-1.1B-Chat-v1.0 --n-steps 500
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:
    print(f"missing dependency: {e}", file=sys.stderr)
    print("install with: pip install torch transformers", file=sys.stderr)
    sys.exit(1)

from resileos.substrate.aggregate_carrier import (
    AggregateCarrier,
    build_aggregate_features,
)


# ── facts ──────────────────────────────────────────────────────────────


def load_facts(path: Path) -> list[tuple[str, str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts = []
    for row in raw.get("facts", []):
        if isinstance(row, (list, tuple)) and len(row) == 3:
            s, r, o = (str(x).strip() for x in row)
            if s and r and o:
                facts.append((s, r, o))
    return facts


# ── tokenization ──────────────────────────────────────────────────────


def tokenize_fact(
    tokenizer, fact: tuple[str, str, str]
) -> Optional[tuple[list[int], list[int], list[bool]]]:
    """Returns (input_ids, targets, loss_mask) or None if degenerate.

    input_ids = full[:-1]
    targets   = full[1:]
    loss_mask is True on target positions that predict object tokens.
    """
    s, r, o = fact
    prefix = tokenizer.encode(
        f"{s} {r}", add_special_tokens=False
    )
    obj = tokenizer.encode(f" {o}", add_special_tokens=False)
    if len(prefix) < 1 or len(obj) < 1:
        return None
    full = prefix + obj
    if len(full) < 2:
        return None
    input_ids = full[:-1]
    targets = full[1:]
    loss_mask = [False] * (len(prefix) - 1) + [True] * len(obj)
    if len(loss_mask) != len(targets):
        return None
    return input_ids, targets, loss_mask


# ── batching ──────────────────────────────────────────────────────────


def collate(
    tokenized: list,
    indices: list[int],
    pad_id: int,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    batch = [tokenized[i] for i in indices]
    max_len = max(len(inp[0]) for inp in batch)
    B = len(batch)
    input_ids = torch.full((B, max_len), pad_id, dtype=torch.long)
    attn = torch.zeros((B, max_len), dtype=torch.long)
    targets = torch.full((B, max_len), -100, dtype=torch.long)
    loss_mask = torch.zeros((B, max_len), dtype=torch.bool)
    for i, (inp, tgt, lm) in enumerate(batch):
        input_ids[i, : len(inp)] = torch.tensor(inp, dtype=torch.long)
        attn[i, : len(inp)] = 1
        targets[i, : len(tgt)] = torch.tensor(tgt, dtype=torch.long)
        loss_mask[i, : len(lm)] = torch.tensor(lm, dtype=torch.bool)
    return (
        input_ids.to(device),
        attn.to(device),
        targets.to(device),
        loss_mask.to(device),
    )


# ── forward ───────────────────────────────────────────────────────────


def masked_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    loss_mask: torch.Tensor,
    vocab: int,
) -> tuple[torch.Tensor, int]:
    per_tok = F.cross_entropy(
        logits.view(-1, vocab),
        targets.view(-1),
        reduction="none",
        ignore_index=-100,
    ).view(targets.shape)
    selected = per_tok[loss_mask]
    n = int(loss_mask.sum())
    return selected.sum(), n


# ── measurement ───────────────────────────────────────────────────────


@torch.no_grad()
def measure_nll(
    decoder,
    tokenizer,
    facts: list,
    tokenized: list,
    features: Optional[np.ndarray],
    carrier: Optional[AggregateCarrier],
    device: torch.device,
    batch_size: int,
    vocab: int,
    pad_id: int,
) -> float:
    total_loss = 0.0
    total_tokens = 0
    decoder.eval()
    if carrier is not None:
        carrier.eval()
    n = len(tokenized)
    for start in range(0, n, batch_size):
        idx = list(range(start, min(start + batch_size, n)))
        input_ids, attn, targets, loss_mask = collate(
            tokenized, idx, pad_id, device
        )
        logits = decoder(input_ids=input_ids, attention_mask=attn).logits
        if carrier is not None and features is not None:
            feat_batch = torch.tensor(
                features[idx], dtype=torch.float32, device=device
            )
            bias = carrier(feat_batch)
            logits = logits + bias.unsqueeze(1)
        loss_sum, n_tok = masked_loss(logits, targets, loss_mask, vocab)
        total_loss += float(loss_sum)
        total_tokens += n_tok
    return total_loss / max(total_tokens, 1)


# ── training ──────────────────────────────────────────────────────────


def train_carrier(
    decoder,
    tokenized: list,
    features: np.ndarray,
    device: torch.device,
    n_steps: int,
    batch_size: int,
    seed: int,
    vocab: int,
    pad_id: int,
    log_every: int = 50,
) -> AggregateCarrier:
    torch.manual_seed(seed)
    carrier = AggregateCarrier(
        input_dim=features.shape[1],
        output_dim=vocab,
        hidden_dim=64,
    ).to(device)
    opt = torch.optim.AdamW(carrier.parameters(), lr=1e-3)
    decoder.eval()
    carrier.train()

    rng = np.random.default_rng(seed)
    n = len(tokenized)

    for step in range(n_steps):
        indices = rng.permutation(n)
        step_loss = 0.0
        step_tokens = 0
        opt.zero_grad()
        for start in range(0, n, batch_size):
            idx = [int(i) for i in indices[start : start + batch_size]]
            input_ids, attn, targets, loss_mask = collate(
                tokenized, idx, pad_id, device
            )
            feat_batch = torch.tensor(
                features[idx], dtype=torch.float32, device=device
            )
            bias = carrier(feat_batch)
            logits = decoder(
                input_ids=input_ids, attention_mask=attn
            ).logits
            logits = logits + bias.unsqueeze(1)
            loss_sum, n_tok = masked_loss(logits, targets, loss_mask, vocab)
            if n_tok == 0:
                continue
            loss = loss_sum / n_tok
            loss.backward()
            step_loss += float(loss_sum)
            step_tokens += n_tok
        opt.step()
        if (step + 1) % log_every == 0:
            avg = step_loss / max(step_tokens, 1)
            print(
                f"  step {step + 1:4d}  loss={avg:.4f}  "
                f"scale={float(carrier.bias_scale):.4f}"
            )

    return carrier


# ── main ──────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate training probe")
    ap.add_argument(
        "--decoder",
        type=str,
        default="Qwen/Qwen2.5-0.5B",
        help="HF model id (Qwen/Qwen2.5-0.5B or TinyLlama/...)",
    )
    ap.add_argument(
        "--facts", type=str, default="configs/titanos-facts.json"
    )
    ap.add_argument("--n-steps", type=int, default=500)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--kappa-on", type=float, default=2.0)
    ap.add_argument("--n-engines", type=int, default=3)
    ap.add_argument("--feature-steps", type=int, default=10)
    ap.add_argument("--device", type=str, default="auto")
    ap.add_argument(
        "--out", type=str, default="artifacts/report_aggregate_training_probe.json"
    )
    args = ap.parse_args()

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    facts_path = Path(args.facts)
    if not facts_path.exists():
        print(f"facts not found: {facts_path}", file=sys.stderr)
        return 1
    facts = load_facts(facts_path)
    if not facts:
        print(f"no facts in {facts_path}", file=sys.stderr)
        return 1
    print(f"loaded {len(facts)} facts")

    print(f"loading decoder {args.decoder} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(args.decoder)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    decoder = AutoModelForCausalLM.from_pretrained(
        args.decoder, torch_dtype=torch.float32
    ).to(device)
    decoder.eval()
    for p in decoder.parameters():
        p.requires_grad_(False)

    vocab = int(decoder.config.vocab_size)
    pad_id = int(tokenizer.pad_token_id)
    print(f"vocab={vocab}  pad_id={pad_id}")

    tokenized = []
    kept_facts = []
    for fact in facts:
        t = tokenize_fact(tokenizer, fact)
        if t is not None:
            tokenized.append(t)
            kept_facts.append(fact)
    if len(tokenized) < len(facts):
        print(
            f"kept {len(tokenized)}/{len(facts)} facts after tokenization"
        )
    if not tokenized:
        print("no tokenizable facts", file=sys.stderr)
        return 1

    print(f"building κ=0 features (N={args.n_engines})...")
    feats_off = build_aggregate_features(
        kept_facts,
        n_engines=args.n_engines,
        kappa=0.0,
        n_steps_per_fact=args.feature_steps,
        seed=args.seed,
    )
    print(f"building κ={args.kappa_on} features...")
    feats_on = build_aggregate_features(
        kept_facts,
        n_engines=args.n_engines,
        kappa=args.kappa_on,
        n_steps_per_fact=args.feature_steps,
        seed=args.seed,
    )
    assert feats_off.shape == feats_on.shape
    print(f"feature_dim: {feats_off.shape[1]}")

    print("measuring baseline (no carrier)...")
    baseline_nll = measure_nll(
        decoder, tokenizer, kept_facts, tokenized,
        features=None, carrier=None, device=device,
        batch_size=args.batch_size, vocab=vocab, pad_id=pad_id,
    )
    print(f"  baseline NLL: {baseline_nll:.4f}")

    print(f"training carrier on κ=0 features ({args.n_steps} steps)...")
    carrier_off = train_carrier(
        decoder, tokenized, feats_off, device,
        n_steps=args.n_steps, batch_size=args.batch_size,
        seed=args.seed, vocab=vocab, pad_id=pad_id,
    )
    nll_off = measure_nll(
        decoder, tokenizer, kept_facts, tokenized,
        features=feats_off, carrier=carrier_off, device=device,
        batch_size=args.batch_size, vocab=vocab, pad_id=pad_id,
    )
    print(f"  κ=0 NLL: {nll_off:.4f}")

    print(f"training carrier on κ={args.kappa_on} features...")
    carrier_on = train_carrier(
        decoder, tokenized, feats_on, device,
        n_steps=args.n_steps, batch_size=args.batch_size,
        seed=args.seed, vocab=vocab, pad_id=pad_id,
    )
    nll_on = measure_nll(
        decoder, tokenizer, kept_facts, tokenized,
        features=feats_on, carrier=carrier_on, device=device,
        batch_size=args.batch_size, vocab=vocab, pad_id=pad_id,
    )
    print(f"  κ={args.kappa_on} NLL: {nll_on:.4f}")

    improvement_vs_baseline = baseline_nll - nll_on
    improvement_kappa = nll_off - nll_on
    if improvement_kappa > 0.02:
        verdict = (
            "coupling reduces object-token NLL vs κ=0 control — "
            "Path B validated on this task"
        )
    elif improvement_kappa < -0.02:
        verdict = (
            "coupling increases NLL vs κ=0 — "
            "aggregate features may be misleading the carrier"
        )
    else:
        verdict = (
            "no measurable coupled advantage — "
            "aggregate signal does not reduce decoder loss"
        )

    report = {
        "probe": "aggregate_training",
        "decoder": args.decoder,
        "facts_path": str(facts_path),
        "n_facts_loaded": len(facts),
        "n_facts_used": len(kept_facts),
        "n_steps": args.n_steps,
        "n_engines": args.n_engines,
        "kappa_on": args.kappa_on,
        "kappa_off": 0.0,
        "feature_dim": int(feats_off.shape[1]),
        "vocab": vocab,
        "baseline_nll": baseline_nll,
        "nll_kappa_off": nll_off,
        "nll_kappa_on": nll_on,
        "improvement_vs_baseline": improvement_vs_baseline,
        "improvement_kappa": improvement_kappa,
        "carrier_off_params": carrier_off.describe(),
        "carrier_on_params": carrier_on.describe(),
        "carrier_off_scale_final": float(carrier_off.bias_scale),
        "carrier_on_scale_final": float(carrier_on.bias_scale),
        "verdict": verdict,
        "notes": [
            "Input is aggregate (R + M_triu + mean_F_res), NOT per-engine lat_s_k.",
            "Ablation is kappa only; input dimension matched.",
            "Logit bias only; embedding-bias ablation is future work.",
            "Object-token NLL only; prefix predictions are masked out.",
            "load-bearing number is improvement_kappa = nll_k0 - nll_k2.",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    print()
    print(f"baseline NLL:       {baseline_nll:.4f}")
    print(f"κ=0 carrier NLL:    {nll_off:.4f}")
    print(f"κ={args.kappa_on} carrier NLL:    {nll_on:.4f}")
    print(f"vs baseline:        {improvement_vs_baseline:+.4f}")
    print(f"improvement (κ):    {improvement_kappa:+.4f}")
    print(f"verdict: {verdict}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
