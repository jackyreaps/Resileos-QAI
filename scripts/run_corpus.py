#!/usr/bin/env python3
"""
Run a real corpus through the composed pipeline.

Loads Koine Greek (default), fits a CharTokenizer, windows the text,
and feeds each window through LanguagePipeline. Reports R trajectory,
round-trip accuracy, reaper and φ-compress firing rates.

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
    CharTokenizer, load_corpus,
    KoineGreekSource, GutenbergSource, PlainTextSource, SyntheticSource,
)


# ── pipeline import with a clear error ──────────────────────────────────
def _make_pipeline(**kwargs: Any) -> Any:
    """
    Load LanguagePipeline from resileos.pipeline.

    If the class name differs in your tree, change the import and the
    constructor call here. Everything else in this runner is decoupled
    from the pipeline's internal API.
    """
    try:
        from resileos.pipeline import LanguagePipeline  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            f"could not import LanguagePipeline from resileos.pipeline: {e}\n"
            "Adjust _make_pipeline() in scripts/run_corpus.py to match "
            "your class name."
        )
    return LanguagePipeline(**kwargs)


# ── tokenizer fit ───────────────────────────────────────────────────────
def fit_tokenizer(text: str, strip_diacritics: bool) -> CharTokenizer:
    tok = CharTokenizer(strip_diacritics=strip_diacritics)
    tok.fit(text)
    return tok


# ── windowing ───────────────────────────────────────────────────────────
def window_ids(ids: list[int], window: int, stride: int
               ) -> list[list[int]]:
    if window <= 0 or stride <= 0:
        raise ValueError("window and stride must be positive")
    if len(ids) < window:
        return [ids] if ids else []
    out = []
    i = 0
    while i + window <= len(ids):
        out.append(ids[i:i + window])
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
    p.add_argument("--source", default="koine",
                   choices=["koine", "gutenberg", "synthetic", "plain"])
    p.add_argument("--path", default=None,
                   help="path for --source plain")
    p.add_argument("--target-chars", type=int, default=8000)
    p.add_argument("--window", type=int, default=32)
    p.add_argument("--stride", type=int, default=16)
    p.add_argument("--strip-diacritics", action="store_true")
    p.add_argument("--gutenberg-index", type=int, default=0)
    p.add_argument("--alphabet", default="abcdefghijklmnopqrstuvwxyz ")
    p.add_argument("--length", type=int, default=4000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "report_corpus.json"))

    # Pipeline kwargs (mirrors PipelineConfig defaults we've seen).
    p.add_argument("--vocab-override", type=int, default=None,
                   help="override vocab_size passed to the pipeline; "
                        "default is tokenizer vocab size")
    p.add_argument("--dim", type=int, default=512)
    p.add_argument("--max-positions", type=int, default=512)
    args = p.parse_args()

    # ── load corpus ─────────────────────────────────────────────────
    source = _build_source(args)
    print(f"[corpus] source           = {args.source}")
    text = load_corpus(source, target_chars=args.target_chars)
    print(f"[corpus] chars            = {len(text)}")
    print(f"[corpus] first 60 chars   = {text[:60]!r}")

    # ── tokenizer ───────────────────────────────────────────────────
    tok = fit_tokenizer(text, strip_diacritics=args.strip_diacritics)
    print(f"[token] vocab_size        = {tok.vocab_size}")
    print(f"[token] strip_diacritics  = {tok.strip_diacritics}")
    print(f"[token] first 20 chars    = {''.join(tok._chars[:20])!r}")

    ids = tok.encode(text)
    print(f"[token] ids               = {len(ids)}")

    # ── pipeline ────────────────────────────────────────────────────
    vocab_size = args.vocab_override or tok.vocab_size
    pipe = _make_pipeline(
        vocab_size=vocab_size,
        dim=args.dim,
        max_positions=args.max_positions,
    )
    print(f"[pipe]  vocab_size        = {vocab_size}")
    print(f"[pipe]  dim               = {args.dim}")

    # ── windows ─────────────────────────────────────────────────────
    windows = window_ids(ids, args.window, args.stride)
    print(f"[run]   windows           = {len(windows)}")
    print()

    r_trajectory: list[float] = []
    token_acc: list[float] = []
    exact_match: list[bool] = []
    reaper_fired = 0
    compress_fired = 0
    recon: list[float] = []

    for i, window in enumerate(windows):
        result = pipe.step(window)
        recovered = _extract_recovered(result)
        R = _extract_R(result)
        rec = _extract_reconstruction(result)
        reaper = _extract_flag(result, "reaper_fired")
        comp = _extract_flag(result, "compress_fired")

        r_trajectory.append(R)
        recon.append(rec)
        if reaper:
            reaper_fired += 1
        if comp:
            compress_fired += 1

        n = len(window)
        match = sum(1 for a, b in zip(window, recovered) if a == b) if recovered else 0
        token_acc.append(match / float(n))
        exact_match.append(bool(recovered) and match == n)

        if (i + 1) % max(1, len(windows) // 8) == 0 or i == 0:
            print(f"  [{i+1:4d}/{len(windows)}] "
                  f"R={R:.4f}  token_acc={token_acc[-1]:.3f}  "
                  f"recon={rec:.4f}  reaper={'Y' if reaper else 'n'}  "
                  f"compress={'Y' if comp else 'n'}")

    print()
    R_mean = float(np.mean(r_trajectory)) if r_trajectory else 0.0
    R_std = float(np.std(r_trajectory)) if r_trajectory else 0.0
    R_min = float(np.min(r_trajectory)) if r_trajectory else 0.0
    R_max = float(np.max(r_trajectory)) if r_trajectory else 0.0
    tok_mean = float(np.mean(token_acc)) if token_acc else 0.0
    exact = int(sum(exact_match))
    rec_mean = float(np.mean(recon)) if recon else 0.0

    print("=== summary ===")
    print(f"  windows:              {len(windows)}")
    print(f"  exact windows:        {exact}/{len(windows)}")
    print(f"  mean token accuracy:  {100.0*tok_mean:.2f}%")
    print(f"  R mean / std:         {R_mean:.4f} / {R_std:.4f}")
    print(f"  R range:              [{R_min:.4f}, {R_max:.4f}]")
    print(f"  mean reconstruction:  {rec_mean:.4f}")
    print(f"  reaper fired:         {reaper_fired}/{len(windows)}")
    print(f"  compress fired:       {compress_fired}/{len(windows)}")

    report = {
        "source": args.source,
        "target_chars": args.target_chars,
        "window": args.window,
        "stride": args.stride,
        "strip_diacritics": tok.strip_diacritics,
        "vocab_size": tok.vocab_size,
        "dim": args.dim,
        "max_positions": args.max_positions,
        "n_windows": len(windows),
        "exact_windows": exact,
        "mean_token_accuracy": tok_mean,
        "R_mean": R_mean, "R_std": R_std,
        "R_min": R_min, "R_max": R_max,
        "mean_reconstruction": rec_mean,
        "reaper_fired": reaper_fired,
        "compress_fired": compress_fired,
        "R_trajectory": r_trajectory,
        "token_accuracy": token_acc,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    return 0


# ── pipeline result extraction ──────────────────────────────────────────
# The pipeline may return a dict, a dataclass, or a namespace. These
# helpers accept any of them and fall back to sensible defaults.
def _get(result: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        if isinstance(result, dict) and n in result:
            return result[n]
        if hasattr(result, n):
            return getattr(result, n)
    return default


def _extract_recovered(result: Any) -> list[int]:
    v = _get(result, "recovered", "decoded", "tokens")
    if v is None:
        return []
    return [int(x) for x in v]


def _extract_R(result: Any) -> float:
    v = _get(result, "R", "order_parameter", "r_value")
    return float(v) if v is not None else 0.0


def _extract_reconstruction(result: Any) -> float:
    v = _get(result, "reconstruction", "recon", "reconstruction_accuracy")
    return float(v) if v is not None else 0.0


def _extract_flag(result: Any, name: str) -> bool:
    v = _get(result, name, name.replace("_fired", ""), default=False)
    return bool(v) if v is not None else False


if __name__ == "__main__":
    raise SystemExit(main())
