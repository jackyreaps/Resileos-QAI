#!/usr/bin/env python3
"""Compression A/B (RES-401 §3).

Runs the language pipeline over a corpus twice: once with
`phi_compress_enabled = False` (baseline) and once with it enabled
(gated), and reports the per-mode summary the RES-401 doc cites:

    Mode | Fire step | Final rank | Final R | Final CSI

CSI is the Causal Sandbox Index (RES-305). If the CSI helpers are
unavailable in the current tree, the per-window CSI column is None and
the summary reports NaN.

Usage:
    python scripts/run_compression_ab.py \
        --source plain --path configs/real-workload-corpus.txt \
        --target-chars 40000 --window 64 --stride 32 --m 22 --n 23 \
        --out artifacts/report_compression_ab.json

    # default corpus: the bundled koine fallback
    python scripts/run_compression_ab.py --out artifacts/report_compression_ab.json
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

from resileos.corpus import (  # noqa: E402
    CharTokenizer,
    load_corpus,
    KoineGreekSource,
    GutenbergSource,
    PlainTextSource,
    SyntheticSource,
)


# ── pipeline construction ───────────────────────────────────────────────
def _make_pipeline(m: int, n: int, **kwargs: Any) -> Any:
    from resileos.pipeline import LanguagePipeline, PipelineConfig

    config = PipelineConfig(dim=m * n, m=m, n=n, **kwargs)
    return LanguagePipeline(config)


# ── tokenizer fit ───────────────────────────────────────────────────────
def _fit_tokenizer(text: str) -> CharTokenizer:
    tok = CharTokenizer(strip_diacritics=False)
    tok.fit(text)
    return tok


# ── windowing ───────────────────────────────────────────────────────────
def _window_ids(ids: list[int], window: int, stride: int) -> list[list[int]]:
    if len(ids) < window:
        return [ids] if ids else []
    out: list[list[int]] = []
    i = 0
    while i + window <= len(ids):
        out.append(ids[i : i + window])
        i += stride
    return out


# ── corpus ──────────────────────────────────────────────────────────────
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


# ── CSI helpers ─────────────────────────────────────────────────────────
def _compute_csi_safe(core: Any, packet: Any) -> Optional[float]:
    """Attempt to compute CSI for the current step. Returns None if the
    helpers are unavailable or their signature does not match this tree.
    """
    try:
        from resileos.substrate.sandbox import (  # type: ignore
            compute_csi,
            volume_residual,
            internal_prediction_error,
        )
    except Exception:
        return None

    try:
        # Best-effort: volume residual from the packet if it carries a
        # volume field; internal prediction error from the core monitors.
        vol = float(getattr(packet, "volume", 0.0))
        bundle = core.monitors() if hasattr(core, "monitors") else None
        if bundle is None:
            return None
        csi_state = compute_csi(
            volume=vol,
            monitors=bundle,
        )
        # compute_csi may return a float or a CSIState; normalise.
        if isinstance(csi_state, (int, float)):
            return float(csi_state)
        return float(getattr(csi_state, "csi", float("nan")))
    except Exception:
        return None


# ── single-mode run ─────────────────────────────────────────────────────
def _run_mode(
    *,
    label: str,
    phi_compress_enabled: bool,
    args: argparse.Namespace,
    text: str,
    tok: CharTokenizer,
) -> dict:
    dim = args.m * args.n
    max_pos = max(args.window, 64, 512)

    pipeline = _make_pipeline(
        m=args.m,
        n=args.n,
        vocab_size=tok.vocab_size,
        max_positions=max_pos,
        phi_compress_enabled=phi_compress_enabled,
        phi_compress_warmup=args.phi_compress_warmup,
        phi_compress_min_R=args.phi_compress_min_R,
        r=min(8, args.m, args.n),
    )

    ids = tok.encode(text)
    windows = _window_ids(ids, args.window, args.stride)

    per_window: list[dict] = []
    for i, w in enumerate(windows):
        result = pipeline.step(w)
        csi = _compute_csi_safe(pipeline.core, result)
        per_window.append({
            "w_idx": i,
            "R": float(result.order_parameter),
            "epsilon": float(result.epsilon),
            "rank_used": int(result.rank_used),
            "reaper_fraction": float(result.reaper_fraction),
            "recon_rel_error": float(result.reconstruction_rel_error),
            "csi": (None if csi is None else float(csi)),
        })

    stats = pipeline.stats()
    compressions = list(stats.get("compressions", []))
    fire_step = int(compressions[0]) if compressions else None

    r_arr = np.array([row["R"] for row in per_window], dtype=float)
    csi_vals = [row["csi"] for row in per_window if row["csi"] is not None]
    final_csi = float(csi_vals[-1]) if csi_vals else float("nan")
    at_fire_csi = (
        float(per_window[fire_step]["csi"])
        if fire_step is not None
        and fire_step < len(per_window)
        and per_window[fire_step]["csi"] is not None
        else float("nan")
    )

    summary = {
        "label": label,
        "phi_compress_enabled": bool(phi_compress_enabled),
        "windows": len(windows),
        "fire_step": fire_step,
        "n_compressions": len(compressions),
        "final_rank": int(stats.get("current_rank", -1)),
        "final_R": float(r_arr[-1]) if r_arr.size else float("nan"),
        "mean_R": float(r_arr.mean()) if r_arr.size else float("nan"),
        "final_csi": final_csi,
        "csi_at_fire": at_fire_csi,
        "per_window": per_window,
    }
    return summary


# ── main ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="koine",
                    choices=["koine", "gutenberg", "synthetic", "plain"])
    ap.add_argument("--path", default=None)
    ap.add_argument("--target-chars", type=int, default=40000)
    ap.add_argument("--window", type=int, default=64)
    ap.add_argument("--stride", type=int, default=32)
    ap.add_argument("--m", type=int, default=22)
    ap.add_argument("--n", type=int, default=23)
    ap.add_argument("--gutenberg-index", type=int, default=0)
    ap.add_argument("--alphabet", default="abc ")
    ap.add_argument("--length", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=0)

    ap.add_argument("--baseline-off", action="store_true", default=True,
                    help="run the no-compress baseline (default: on)")
    ap.add_argument("--gated-on", action="store_true", default=True,
                    help="run the gated compress arm (default: on)")
    ap.add_argument("--phi-compress-warmup", type=int, default=32)
    ap.add_argument("--phi-compress-min-R", type=float, default=0.9)

    ap.add_argument("--out", type=Path,
                    default=Path("artifacts/report_compression_ab.json"))
    args = ap.parse_args()

    if args.m * args.n <= 0:
        raise SystemExit("m*n must be positive")

    # corpus + tokenizer shared across both arms
    source = _build_source(args)
    text = load_corpus(source, target_chars=args.target_chars)
    tok = _fit_tokenizer(text)

    results: list[dict] = []

    if args.baseline_off:
        print("[ab] arm: off (phi_compress_enabled=False)")
        results.append(_run_mode(
            label="off",
            phi_compress_enabled=False,
            args=args,
            text=text,
            tok=tok,
        ))

    if args.gated_on:
        print("[ab] arm: on (phi_compress_enabled=True)")
        results.append(_run_mode(
            label="on",
            phi_compress_enabled=True,
            args=args,
            text=text,
            tok=tok,
        ))

    # stdout summary table
    print()
    print(f"{'mode':<6} {'fire':>6} {'rank':>6} {'final R':>10} "
          f"{'mean R':>10} {'final CSI':>10}")
    for r in results:
        fire = "-" if r["fire_step"] is None else str(r["fire_step"])
        csi = r["final_csi"]
        csi_str = f"{csi:.4f}" if csi == csi else "NaN"  # NaN check
        print(f"{r['label']:<6} {fire:>6} {r['final_rank']:>6} "
              f"{r['final_R']:>10.4f} {r['mean_R']:>10.4f} "
              f"{csi_str:>10}")

    report = {
        "config": {
            "source": args.source,
            "path": args.path,
            "target_chars": args.target_chars,
            "window": args.window,
            "stride": args.stride,
            "m": args.m,
            "n": args.n,
            "dim": args.m * args.n,
            "phi_compress_warmup": args.phi_compress_warmup,
            "phi_compress_min_R": args.phi_compress_min_R,
            "seed": args.seed,
        },
        "corpus_chars": len(text),
        "vocab_size": int(tok.vocab_size),
        "results": results,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(f"\n[write] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
