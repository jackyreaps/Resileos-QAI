#!/usr/bin/env python3
"""
Run the language pipeline over a corpus.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --config configs/pipeline-config.json \
        --corpus configs/tiny-corpus.txt --out report_pipeline.json

Reports per-sequence:
    input tokens, recovered tokens, exact match, R, gate state,
    reconstruction error, reaper fraction, rank used.

Reports aggregate:
    recovery accuracy, mean R, mean reconstruction error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.pipeline import (
    PipelineConfig, LanguagePipeline, load_corpus,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config",
                   default=str(ROOT / "configs" / "pipeline-config.json"))
    p.add_argument("--corpus",
                   default=str(ROOT / "configs" / "tiny-corpus.txt"))
    p.add_argument("--out", default=str(ROOT / "report_pipeline.json"))
    args = p.parse_args()

    cfg_path = Path(args.config)
    corpus_path = Path(args.corpus)
    if not cfg_path.exists():
        print(f"missing config: {cfg_path}", file=sys.stderr)
        return 2
    if not corpus_path.exists():
        print(f"missing corpus: {corpus_path}", file=sys.stderr)
        return 2

    cfg = PipelineConfig.from_json(cfg_path)
    cfg.validate()
    corpus = load_corpus(corpus_path)
    if not corpus:
        print("empty corpus", file=sys.stderr)
        return 2

    pipeline = LanguagePipeline(cfg)

    print(f"dim={cfg.dim}  vocab={cfg.vocab_size}  "
          f"m={cfg.m} n={cfg.n} r={cfg.r}  "
          f"n_layers={cfg.n_residual_layers}  "
          f"reaper_n_saved={cfg.reaper_n_saved}")
    print()

    results = []
    total_tokens = 0
    correct_tokens = 0
    R_values = []
    recon_errors = []

    for i, seq in enumerate(corpus):
        result = pipeline.step(seq)
        results.append(result.to_dict())

        exact = result.recovered_exactly
        n_correct = sum(
            1 for a, b in zip(result.input_tokens, result.recovered) if a == b)
        total_tokens += len(result.input_tokens)
        correct_tokens += n_correct
        R_values.append(result.order_parameter)
        recon_errors.append(result.reconstruction_rel_error)

        mark = "OK " if exact else "   "
        print(f"[{i:2d}] {mark} in={seq}  out={result.recovered}  "
              f"n_correct={n_correct}/{len(seq)}")
        print(f"       R={result.order_parameter:.3f}  "
              f"gate={result.gate_state:9s}  "
              f"eps={result.epsilon:.4f}  "
              f"recon={result.reconstruction_rel_error:.4f}  "
              f"reaper={result.reaper_fraction:.3f}  "
              f"rank={result.rank_used}")

    accuracy = 100.0 * correct_tokens / max(total_tokens, 1)
    exact_seqs = sum(1 for r in results if r["input_tokens"] == r["recovered"])

    print()
    print("=== aggregate ===")
    print(f"sequences:              {len(results)}")
    print(f"exact sequences:        {exact_seqs}/{len(results)}")
    print(f"token accuracy:         {accuracy:.1f}%  "
          f"({correct_tokens}/{total_tokens})")
    print(f"mean order parameter:   {np.mean(R_values):.4f}")
    print(f"mean reconstruction:    {np.mean(recon_errors):.4f}")
    print(f"pipeline steps:         {pipeline.stats()['step_count']}")
    print(f"compressions fired:     {pipeline.stats()['compressions']}")

    report = {
        "config": cfg.to_dict(),
        "results": results,
        "aggregate": {
            "n_sequences": len(results),
            "n_exact": exact_seqs,
            "token_accuracy_pct": accuracy,
            "mean_order_parameter": float(np.mean(R_values)),
            "mean_reconstruction_error": float(np.mean(recon_errors)),
            "pipeline_stats": pipeline.stats(),
        },
    }
    Path(args.out).write_text(json.dumps(report, indent=2, default=float))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
