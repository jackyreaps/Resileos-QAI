#!/usr/bin/env python3
"""Demo: incremental views on titanos-facts (no attractor, no GPU)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.substrate.incremental_views import TripleViews, hashed_triple_features


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", default="configs/titanos-facts.json")
    ap.add_argument("--feature-dim", type=int, default=32)
    ap.add_argument("--out", default="artifacts/report_incremental_views.json")
    args = ap.parse_args()

    raw = json.loads(Path(args.facts).read_text())
    facts = [tuple(x) for x in raw.get("facts", []) if len(x) == 3]
    fn = hashed_triple_features(args.feature_dim, seed=0)
    views = TripleViews(feature_dim=args.feature_dim, feature_fn=fn)

    t0 = time.perf_counter()
    n = views.learn_many(facts)
    dt = time.perf_counter() - t0

    report = {
        "n_facts": n,
        "learn_many_s": dt,
        "per_fact_us": (dt / max(n, 1)) * 1e6,
        "snapshot": views.snapshot(),
        "top_relations": views.top_relations(10),
        "notes": [
            "F-IVM-inspired local views; O(1) per learn_delta.",
            "Does not touch Titanos bands or attractor.",
            "Optional CovariancePayload via hashed_triple_features.",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"facts={n} time={dt:.4f}s per_fact={report['per_fact_us']:.1f}us")
    print(f"top relations: {report['top_relations'][:5]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
