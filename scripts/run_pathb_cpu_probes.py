#!/usr/bin/env python3
"""Path B CPU probes (RES-326 §2).

Two CPU-feasible probes that confirm the aggregate -> carrier -> readout
mechanism without a pretrained decoder:

    closed_vocab      — 7-dim aggregate -> MLP -> N_objects-way CE
    mini_transformer  — 7-dim aggregate -> MLP -> logit bias -> frozen
                        random mini-Transformer, next-token CE on the
                        object position

Both use AggregateCarrier (RES-315 §2) on the 7-dim aggregate from
build_aggregate_features (RES-319 §5). Both ablate κ=0 vs κ=2.

The pretrained-decoder probe is the actual Path B research question
(RES-326 §5). This script does not answer it. It answers "does the
mechanism work at all?" — and yes, it does.

Results vary slightly across runs due to random initialization of the
carrier and the mini-Transformer. The sign of Δ (κ=2 vs κ=0) is the
robust finding; the magnitude is seed-dependent.

Usage:
    python scripts/run_pathb_cpu_probes.py --mode both
    python scripts/run_pathb_cpu_probes.py --mode closed_vocab
    python scripts/run_pathb_cpu_probes.py --mode mini_transformer
    python scripts/run_pathb_cpu_probes.py --mode both --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.aggregate_carrier import (  # noqa: E402
    AggregateCarrier,
    build_aggregate_features,
)


# ── data ──────────────────────────────────────────────────────────────


def load_facts(path: Path) -> list[tuple[str, str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts: list[tuple[str, str, str]] = []
    for row in raw.get("facts", []):
        if isinstance(row, (list, tuple)) and len(row) == 3:
            s, r, o = (str(x).strip() for x in row)
            if s and r and o:
                facts.append((s, r, o))
    return facts


# ── probe A: closed-vocab carrier ─────────────────────────────────────


def run_closed_vocab(
    features: np.ndarray,
    object_ids: list[int],
    n_epochs: int = 200,
    batch_size: int = 32,
    lr: float = 1e-3,
    seed: int = 0,
) -> tuple[AggregateCarrier, float, float]:
    """Train AggregateCarrier to classify object IDs from 7-dim features.

    Returns (carrier, final_nll, final_accuracy). NLL and accuracy are
    in-sample: this is a mechanism probe, not a generalization test.
    """
    n = len(object_ids)
    n_objects = int(max(object_ids)) + 1

    torch.manual_seed(seed)
    carrier = AggregateCarrier(
        input_dim=features.shape[1],
        output_dim=n_objects,
        hidden_dim=64,
        n_hidden_layers=2,
    )
    opt = torch.optim.AdamW(carrier.parameters(), lr=lr)

    feats = torch.tensor(features, dtype=torch.float32)
    targets = torch.tensor(object_ids, dtype=torch.long)

    rng = np.random.default_rng(seed)

    for _ in range(n_epochs):
        idx = rng.permutation(n)
        carrier.train()
        for start in range(0, n, batch_size):
            b = idx[start : start + batch_size]
            logits = carrier(feats[b])
            loss = F.cross_entropy(logits, targets[b])
            opt.zero_grad()
            loss.backward()
            opt.step()

    carrier.eval()
    with torch.no_grad():
        logits = carrier(feats)
        nll = float(F.cross_entropy(logits, targets).item())
        preds = logits.argmax(dim=1)
        acc = float((preds == targets).float().mean().item())

    return carrier, nll, acc


# ── probe B: mini-transformer with logit bias ─────────────────────────


class FrozenMiniTransformer(nn.Module):
    """Small frozen transformer for the mini-transformer probe.

    Random initialization, frozen parameters. Produces per-position
    logits. The carrier adds a per-example logit bias on top.
    """

    def __init__(
        self,
        vocab_size: int,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 1,
        max_len: int = 16,
        seed: int = 0,
    ) -> None:
        super().__init__()
        torch.manual_seed(seed)
        self.embed = nn.Embedding(vocab_size, d_model)
        self.pos = nn.Embedding(max_len, d_model)
        self.layers = nn.ModuleList([
            nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=n_heads,
                dim_feedforward=4 * d_model,
                batch_first=True,
                activation="gelu",
                dropout=0.0,
            )
            for _ in range(n_layers)
        ])
        self.lm_head = nn.Linear(d_model, vocab_size, bias=False)
        for p in self.parameters():
            if p.dim() >= 2:
                nn.init.xavier_uniform_(p)
            else:
                nn.init.zeros_(p)
            p.requires_grad_(False)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        B, T = input_ids.shape
        pos_ids = torch.arange(T, device=input_ids.device).unsqueeze(0).expand(B, T)
        x = self.embed(input_ids) + self.pos(pos_ids)
        for layer in self.layers:
            x = layer(x)
        return self.lm_head(x)


def build_mt_vocab(facts: list[tuple[str, str, str]]) -> dict[str, int]:
    """Vocabulary: 3 specials + every entity or relation that appears."""
    entities = {s for s, r, o in facts} | {o for s, r, o in facts}
    relations = {r for s, r, o in facts}
    tokens = sorted(entities | relations)
    vocab = {"<pad>": 0, "<bos>": 1, "<sep>": 2}
    for i, t in enumerate(tokens):
        vocab[t] = 3 + i
    return vocab


def encode_facts_mt(
    facts: list[tuple[str, str, str]],
    vocab: dict[str, int],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Encode each fact as [BOS, s, SEP, r, SEP] -> target object token.

    The target is the token AFTER the last SEP, which the decoder has
    not seen. The carrier's aggregate bias is added at the last
    position (predicting the object).
    """
    BOS = vocab["<bos>"]
    SEP = vocab["<sep>"]
    inputs = []
    targets = []
    for s, r, o in facts:
        inputs.append([BOS, vocab[s], SEP, vocab[r], SEP])
        targets.append(vocab[o])
    return (
        torch.tensor(inputs, dtype=torch.long),
        torch.tensor(targets, dtype=torch.long),
    )


def run_mini_transformer(
    features: np.ndarray,
    inputs: torch.Tensor,
    targets: torch.Tensor,
    vocab_size: int,
    n_epochs: int = 300,
    batch_size: int = 32,
    lr: float = 1e-3,
    seed: int = 0,
) -> tuple[AggregateCarrier, float, float, float, float]:
    """Train carrier logit bias on a frozen mini-transformer.

    Returns (carrier, nll, acc, baseline_nll, baseline_acc). Baseline
    is the frozen decoder with NO carrier bias.
    """
    n = inputs.shape[0]

    torch.manual_seed(seed)
    decoder = FrozenMiniTransformer(vocab_size=vocab_size, seed=seed)
    carrier = AggregateCarrier(
        input_dim=features.shape[1],
        output_dim=vocab_size,
        hidden_dim=64,
        n_hidden_layers=2,
    )
    opt = torch.optim.AdamW(carrier.parameters(), lr=lr)

    feats = torch.tensor(features, dtype=torch.float32)

    # Frozen decoder logits don't change during training; compute once.
    with torch.no_grad():
        decoder_logits = decoder(inputs)[:, -1, :]  # (N, vocab)

    baseline_nll = float(
        F.cross_entropy(decoder_logits, targets).item()
    )
    baseline_acc = float(
        (decoder_logits.argmax(dim=1) == targets).float().mean().item()
    )

    rng = np.random.default_rng(seed)

    for _ in range(n_epochs):
        idx = rng.permutation(n)
        carrier.train()
        for start in range(0, n, batch_size):
            b = idx[start : start + batch_size]
            bias = carrier(feats[b])
            combined = decoder_logits[b] + bias
            loss = F.cross_entropy(combined, targets[b])
            opt.zero_grad()
            loss.backward()
            opt.step()

    carrier.eval()
    with torch.no_grad():
        bias = carrier(feats)
        combined = decoder_logits + bias
        nll = float(F.cross_entropy(combined, targets).item())
        acc = float(
            (combined.argmax(dim=1) == targets).float().mean().item()
        )

    return carrier, nll, acc, baseline_nll, baseline_acc


# ── main ──────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Path B CPU probes (RES-326 §2)"
    )
    ap.add_argument(
        "--mode",
        choices=["closed_vocab", "mini_transformer", "both"],
        default="both",
    )
    ap.add_argument("--facts", default="configs/titanos-facts.json")
    ap.add_argument("--n-epochs-cv", type=int, default=200)
    ap.add_argument("--n-epochs-mt", type=int, default=300)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--kappa-on", type=float, default=2.0)
    ap.add_argument("--n-engines", type=int, default=3)
    ap.add_argument("--feature-steps", type=int, default=10)
    ap.add_argument(
        "--out", default="artifacts/report_pathb_cpu_probes.json"
    )
    args = ap.parse_args()

    facts_path = Path(args.facts)
    if not facts_path.exists():
        print(f"facts not found: {facts_path}", file=sys.stderr)
        return 1
    facts = load_facts(facts_path)
    if not facts:
        print(f"no facts in {facts_path}", file=sys.stderr)
        return 1
    print(f"loaded {len(facts)} facts")

    print("building κ=0 features...")
    feats_off = build_aggregate_features(
        facts,
        n_engines=args.n_engines,
        kappa=0.0,
        n_steps_per_fact=args.feature_steps,
        seed=args.seed,
    )
    print(f"building κ={args.kappa_on} features...")
    feats_on = build_aggregate_features(
        facts,
        n_engines=args.n_engines,
        kappa=args.kappa_on,
        n_steps_per_fact=args.feature_steps,
        seed=args.seed,
    )
    print(f"feature dim: {feats_off.shape[1]}")

    report: dict = {
        "n_facts": len(facts),
        "feature_dim": int(feats_off.shape[1]),
        "config": {
            "mode": args.mode,
            "seed": args.seed,
            "kappa_on": args.kappa_on,
            "n_engines": args.n_engines,
            "feature_steps": args.feature_steps,
            "n_epochs_cv": args.n_epochs_cv,
            "n_epochs_mt": args.n_epochs_mt,
            "batch_size": args.batch_size,
            "lr": args.lr,
        },
    }

    # ── Probe A: closed vocab ────────────────────────────────────────
    if args.mode in ("closed_vocab", "both"):
        print("\n── closed_vocab probe ──")
        objects = sorted({o for s, r, o in facts})
        obj_to_id = {o: i for i, o in enumerate(objects)}
        obj_ids = [obj_to_id[o] for s, r, o in facts]
        print(f"n_objects: {len(objects)}")

        _, nll_off, acc_off = run_closed_vocab(
            feats_off,
            obj_ids,
            n_epochs=args.n_epochs_cv,
            batch_size=args.batch_size,
            lr=args.lr,
            seed=args.seed,
        )
        _, nll_on, acc_on = run_closed_vocab(
            feats_on,
            obj_ids,
            n_epochs=args.n_epochs_cv,
            batch_size=args.batch_size,
            lr=args.lr,
            seed=args.seed,
        )

        print(
            f"  κ=0: acc={acc_off:.3f}  nll={nll_off:.3f}"
        )
        print(
            f"  κ={args.kappa_on}: acc={acc_on:.3f}  nll={nll_on:.3f}"
        )
        print(
            f"  Δacc={acc_on - acc_off:+.3f}  "
            f"Δnll={nll_off - nll_on:+.3f}"
        )

        report["closed_vocab"] = {
            "n_objects": len(objects),
            "kappa_off": {"acc": acc_off, "nll": nll_off},
            "kappa_on": {"acc": acc_on, "nll": nll_on},
            "delta_acc": acc_on - acc_off,
            "improvement_nll": nll_off - nll_on,
            "note": (
                "In-sample. Mechanism probe, not a generalization test."
            ),
        }

    # ── Probe B: mini-transformer ────────────────────────────────────
    if args.mode in ("mini_transformer", "both"):
        print("\n── mini_transformer probe ──")
        vocab = build_mt_vocab(facts)
        vocab_size = len(vocab)
        inputs, targets = encode_facts_mt(facts, vocab)
        print(
            f"vocab: {vocab_size}  input_len: {inputs.shape[1]}"
        )

        _, nll_off, acc_off, base_nll, base_acc = run_mini_transformer(
            feats_off,
            inputs,
            targets,
            vocab_size,
            n_epochs=args.n_epochs_mt,
            batch_size=args.batch_size,
            lr=args.lr,
            seed=args.seed,
        )
        _, nll_on, acc_on, _, _ = run_mini_transformer(
            feats_on,
            inputs,
            targets,
            vocab_size,
            n_epochs=args.n_epochs_mt,
            batch_size=args.batch_size,
            lr=args.lr,
            seed=args.seed,
        )

        print(
            f"  baseline: acc={base_acc:.3f}  nll={base_nll:.3f}"
        )
        print(
            f"  κ=0: acc={acc_off:.3f}  nll={nll_off:.3f}"
        )
        print(
            f"  κ={args.kappa_on}: acc={acc_on:.3f}  nll={nll_on:.3f}"
        )
        print(
            f"  Δacc={acc_on - acc_off:+.3f}  "
            f"Δnll={nll_off - nll_on:+.3f}"
        )

        report["mini_transformer"] = {
            "vocab_size": vocab_size,
            "input_len": int(inputs.shape[1]),
            "baseline_no_carrier": {"acc": base_acc, "nll": base_nll},
            "kappa_off": {"acc": acc_off, "nll": nll_off},
            "kappa_on": {"acc": acc_on, "nll": nll_on},
            "delta_acc": acc_on - acc_off,
            "improvement_nll": nll_off - nll_on,
            "note": (
                "Frozen random mini-Transformer + carrier logit bias. "
                "Baseline is the frozen decoder with no bias."
            ),
        }

    report["notes"] = [
        "Input is the 7-dim aggregate from EngineGroup (RES-318 §6).",
        "closed_vocab: 7-dim -> MLP -> N_objects-way CE. No decoder.",
        "mini_transformer: 7-dim -> MLP -> logit bias -> frozen random "
        "transformer, CE on object position only.",
        "Both are mechanism probes; the pretrained-decoder probe is "
        "separate (RES-326 §5).",
        "Sign of Δ (κ=2 > κ=0) is the robust finding; magnitude is "
        "seed-dependent.",
    ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
