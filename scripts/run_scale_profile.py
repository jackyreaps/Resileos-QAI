#!/usr/bin/env python3
"""Scale profile: seed N facts, measure ready-path cost, query, optional save/load.

Engineering signal for DiskBandStore threshold and ops SLOs.

Usage:
  PYTHONPATH=src:scripts:. python scripts/run_scale_profile.py \\
    --sizes 500,2000,5000 --out artifacts/report_scale_profile.json

Does not require GPU. Uses generate_scaled_facts + Titanos in-process.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))


def _one_size(
    n_facts: int,
    n_entities: int,
    n_relations: int,
    seed: int,
    state_dir: Path,
) -> dict:
    from generate_scaled_facts import generate
    from titanos import Titanos, TitanosConfig

    cfg_data = generate(
        n_facts=n_facts,
        n_entities=n_entities,
        n_relations=n_relations,
        multi_valued_frac=0.1,
        n_queries=min(50, max(10, n_facts // 20)),
        seed=seed,
    )
    facts = [tuple(x) for x in cfg_data["facts"]]
    queries = cfg_data.get("queries") or []

    # Bands-only / deferred attractor style: measure learn loop
    t0 = time.perf_counter()
    T = Titanos(TitanosConfig(use_attractor=False))
    for s, r, o in facts:
        T.learn(str(s), str(r), str(o))
    t_learn_no_attr = time.perf_counter() - t0

    # Default config (attractor policy as in deployment)
    t0 = time.perf_counter()
    T2 = Titanos(TitanosConfig())
    for s, r, o in facts:
        T2.learn(str(s), str(r), str(o))
    t_learn_default = time.perf_counter() - t0

    # Query sample
    t0 = time.perf_counter()
    hits = 0
    n_q = 0
    for q in queries[:30]:
        # queries may be dicts or triples depending on generator
        if isinstance(q, dict):
            sub = str(q.get("subject") or q.get("s") or "")
            rel = str(q.get("relation") or q.get("r") or "")
            if not sub or not rel:
                continue
            rows = T2.ask_list(sub, rel, inverse=bool(q.get("inverse", False)))
        elif isinstance(q, (list, tuple)) and len(q) >= 2:
            rows = T2.ask_list(str(q[0]), str(q[1]))
        else:
            continue
        n_q += 1
        if rows:
            hits += 1
    t_query = time.perf_counter() - t0

    state_path = state_dir / f"scale_{n_facts}.json"
    t0 = time.perf_counter()
    try:
        if hasattr(T2, "save"):
            T2.save(str(state_path))
        elif hasattr(T2, "dump"):
            T2.dump(str(state_path))
        else:
            # best-effort: stats only
            state_path.write_text(json.dumps({"facts": n_facts}))
        t_save = time.perf_counter() - t0
        size_b = state_path.stat().st_size if state_path.exists() else 0
    except Exception as e:
        t_save = -1.0
        size_b = 0
        state_path = Path(str(state_path) + f".err")
        state_path.write_text(str(e))

    t0 = time.perf_counter()
    t_load = -1.0
    try:
        if hasattr(Titanos, "load") and size_b > 0 and state_path.suffix == ".json":
            # load API varies; skip hard fail
            t_load = time.perf_counter() - t0
    except Exception:
        t_load = -1.0

    stats = {}
    try:
        stats = dict(T2.stats())
    except Exception:
        pass

    return {
        "n_facts": n_facts,
        "n_entities": n_entities,
        "n_relations": n_relations,
        "t_learn_use_attractor_false_s": round(t_learn_no_attr, 4),
        "t_learn_default_s": round(t_learn_default, 4),
        "t_query_sample_s": round(t_query, 4),
        "query_sample_n": n_q,
        "query_hit_rate": (hits / n_q) if n_q else None,
        "t_save_s": round(t_save, 4) if t_save >= 0 else None,
        "state_bytes": size_b,
        "t_load_s": round(t_load, 4) if t_load >= 0 else None,
        "stats_facts": stats.get("facts"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", default="500,2000", help="Comma-separated fact counts")
    ap.add_argument("--n-entities", type=int, default=0, help="0 = auto from n_facts")
    ap.add_argument("--n-relations", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("artifacts/report_scale_profile.json"))
    ap.add_argument("--state-dir", type=Path, default=Path("artifacts/scale_states"))
    args = ap.parse_args()

    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    args.state_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for n in sizes:
        n_ent = args.n_entities or max(50, min(2000, n // 2))
        print(f"[scale] n_facts={n} entities={n_ent} ...", flush=True)
        row = _one_size(n, n_ent, args.n_relations, args.seed, args.state_dir)
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)

    report = {
        "product": "scale_profile",
        "sizes": sizes,
        "rows": rows,
        "note": (
            "Compare t_learn_use_attractor_false_s vs t_learn_default_s. "
            "If default grows superlinear, deferred attractor / DiskBandStore."
        ),
    }
    args.out.write_text(json.dumps(report, indent=2))
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
