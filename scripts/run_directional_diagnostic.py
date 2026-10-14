#!/usr/bin/env python3
"""
Directional diagnostic: reconstruction / trend / multi_trend / hybrid(w).

Read-only. Does not modify the main HDRIFT gate, HDRIFTAdapter, or any
frozen contract. Reports the four honest numbers to
report_directional.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.directional import evaluate_modes


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(ROOT / "configs" / "weights.npy"))
    p.add_argument("--out", default=str(ROOT / "report_directional.json"))
    p.add_argument("--r", type=int, default=8)
    p.add_argument("--horizon", type=int, default=4)
    p.add_argument("--trend-window", type=int, default=4)
    p.add_argument("--n-blocks", type=int, default=16)
    p.add_argument("--weights", default="0.0,0.25,1.0",
                   help="comma-separated hybrid trend weights to test")
    args = p.parse_args()

    path = Path(args.data)
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 2

    W = np.load(path)
    blocks = list(W) if W.ndim == 3 else [W]
    if not blocks:
        print("data contains no blocks", file=sys.stderr)
        return 2
    while len(blocks) < args.n_blocks:
        blocks.append(blocks[len(blocks) % len(blocks)])
    blocks = [b.astype(np.float64) for b in blocks[:args.n_blocks]]

    weights = tuple(float(x) for x in args.weights.split(",") if x.strip())

    report = evaluate_modes(
        blocks,
        r=args.r,
        horizon=args.horizon,
        trend_weights=weights,
        trend_window=args.trend_window,
    )
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2))

    print(report["label"])
    print()
    print(f"blocks={report['n_blocks']}  horizon={report['horizon']}  "
          f"r={report['rank']}  trend_window={report['trend_window']}")
    print()
    print(f"reconstruction  "
          f"{report['reconstruction']['reduction_pct']:+7.2f}%  "
          f"(± {report['reconstruction']['reduction_std']:.2f})  "
          f"[tautology]")
    print(f"trend           "
          f"{report['trend']['reduction_pct']:+7.2f}%  "
          f"(± {report['trend']['reduction_std']:.2f})  "
          f"[non-tautological]")
    print(f"multi_trend     "
          f"{report['multi_trend']['reduction_pct']:+7.2f}%  "
          f"(± {report['multi_trend']['reduction_std']:.2f})  "
          f"[non-tautological]")
    for k, v in report["hybrid"].items():
        print(f"hybrid {k:10s} "
              f"{v['reduction_pct']:+7.2f}%  "
              f"(± {v['reduction_std']:.2f})  "
              f"[{v['note']}]")
    print()
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
