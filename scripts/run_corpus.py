#!/usr/bin/env python3
""" Run a real corpus through the composed pipeline. 

Loads Koine Greek (default), fits a CharTokenizer, windows the text, and feeds 
each window through LanguagePipeline. Reports R trajectory, round-trip accuracy,
reaper and φ-compress firing rates. 

Usage:
    python scripts/run_corpus.py
    python scripts/run_corpus.py --target-chars 8000 --window 32 --stride 16
    python scripts/run_corpus.py --source gutenberg --target-chars 8000
    python scripts/run_corpus.py --source synthetic --alphabet "abc " --length 4000
    python scripts/run_corpus.py --source plain --path path/to/file.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.corpus import (
    CharTokenizer,
    load_corpus,
    KoineGreekSource,
    GutenbergSource,
    PlainTextSource,
    SyntheticSource,
)


# ── pipeline import with a clear error ──────────────────────────────────
def _make_pipeline(m: int, n: int, **kwargs: Any) -> Any:
    """ Load LanguagePipeline from resileos.pipeline. 

    The pipeline's dim is set to m * n to satisfy the PipelineConfig
    validation that requires dim == m * n.

    If the class name differs in your tree, change the import and the
    constructor call here. Everything else in this runner is decoupled
    from the pipeline's internal API.
    """
    try:
        from resileos.pipeline import LanguagePipeline, PipelineConfig
    except ImportError as e:
        raise SystemExit(
            f"could not import LanguagePipeline from resileos.pipeline: {e}\n"
            "Adjust _make_pipeline() in scripts/run_corpus.py to match "
            "your class name."
        )

    config = PipelineConfig(dim=m * n, m=m, n=n, **kwargs)
    return LanguagePipeline(config)


# ── tokenizer fit ───────────────────────────────────────────────────────
def fit_tokenizer(text: str, strip_diacritics: bool) -> CharTokenizer:
    tok = CharTokenizer(strip_diacritics=strip_diacritics)
    tok.fit(text)
    return tok


# ── windowing ───────────────────────────────────────────────────────────
def window_ids(ids: list[int], window: int, stride: int) -> list[list[int]]:
    if window <= 0 or stride <= 0:
        raise ValueError("window and stride must be positive")
    if len(ids) < window:
        return [ids] if ids else []
    out = []
    i = 0
    while i + window <= len(ids):
        out.append(ids[i : i + window])
        i += stride
    return out


# ── main ────────────────────────────────────────────────────────────────
def _build_source(args: argparse.Namespace):
    if args.source == "koine":
        return KoineGreekSource()
    if args.source == "gutenberg":
        return GutenbergSource(index=args.gutenberg_index)
    if args.source == "synthetic":
        return SyntheticSource(
            alphabet=args.alphabet,
            length=args.length,
            seed=args.seed,
        )
    if args.source == "plain":
        if not args.path:
            raise SystemExit("--path required for --source plain")
        return PlainTextSource(path=Path(args.path))
    raise SystemExit(f"unknown source: {args.source!r}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="koine", choices=["koine", "gutenberg", "synthetic", "plain"])
    p.add_argument("--path", default=None, help="path for --source plain")
    p.add_argument("--target-chars", type=int, default=8000)
    p.add_argument("--window", type=int, default=32)
    p.add_argument("--stride", type=int, default=16)
    p.add_argument("--strip-diacritics", action="store_true")
    p.add_argument("--gutenberg-index", type=int, default=0)
    p.add_argument("--alphabet", default="abc ")
    p.add_argument("--length", type=int, default=4000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--m", type=int, default=16, help="rows for m*n=dim")
    p.add_argument("--n", type=int, default=16, help="cols for m*n=dim")
    args = p.parse_args()

    # 1. Load corpus
    source = _build_source(args)
    text = load_corpus(source, target_chars=args.target_chars)
    print(f"[corpus] source           = {args.source}")
    print(f"[corpus] chars            = {len(text)}")
    print(f"[corpus] first 60 chars   = {text[:60]!r}")

    # 2. Fit tokenizer
    tok = fit_tokenizer(text, strip_diacritics=args.strip_diacritics)
    print(f"[token] vocab_size        = {tok.vocab_size}")
    print(f"[token] strip_diacritics  = {args.strip_diacritics}")

    # 3. Build pipeline
    pipeline = _make_pipeline(m=args.m, n=args.n)
    dim = args.m * args.n
    print(f"[pipe]  dim               = {dim}")

    # 4. Encode and window
    ids = tok.encode(text)
    windows = window_ids(ids, window=args.window, stride=args.stride)
    print(f"[run]   windows           = {len(windows)}")

    # 5. Run each window through the pipeline
    r_values: list[float] = []
    exact_count = 0
    total_tokens = 0
    correct_tokens = 0
    reaper_fired = 0
    compress_fired = 0
    reconstructions: list[float] = []

    for w in windows:
        result = pipeline.step(w)
        recovered = result.recovered
        r_values.append(float(result.order_parameter))

        if recovered == w:
            exact_count += 1

        total_tokens += len(w)
        correct_tokens += sum(
            1 for a, b in zip(recovered, w) if a == b
        )

        if getattr(result, "reaper_fired", False):
            reaper_fired += 1
        if getattr(result, "compress_fired", False):
            compress_fired += 1
        if hasattr(result, "reconstruction"):
            reconstructions.append(float(result.reconstruction))

    r_arr = np.array(r_values) if r_values else np.array([0.0])
    mean_token_acc = correct_tokens / total_tokens if total_tokens else 0.0

    # 6. Report
    print()
    print("=== summary ===")
    print(f"  windows:              {len(windows)}")
    print(f"  exact windows:        {exact_count}/{len(windows)}")
    print(f"  mean token accuracy:  {mean_token_acc * 100:.2f}%")
    print(f"  R mean / std:         {r_arr.mean():.4f} / {r_arr.std():.4f}")
    print(f"  R range:              [{r_arr.min():.4f}, {r_arr.max():.4f}]")
    if reconstructions:
        print(f"  mean reconstruction:  {np.mean(reconstructions):.4f}")
    print(f"  reaper fired:         {reaper_fired}/{len(windows)}")
    print(f"  compress fired:       {compress_fired}/{len(windows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
