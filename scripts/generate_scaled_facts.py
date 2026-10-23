#!/usr/bin/env python3
"""Generate a synthetic facts config at a target size.

Produces entities, relations, facts, and queries with controlled density.
For engineering signals only — the fact content is synthetic, the
query semantics are identical to configs/titanos-facts.json.

Purpose: measure when the in-memory band store becomes a bottleneck.
At what n_facts does /ready time exceed operational threshold? When
does titanos_live_state.json grow past reasonable sizes? When does
DiskBandStore (RES-320) become mandatory?

Note on cardinality: like the myth config, some (subject, relation)
pairs are multi-valued. /api/v1/query returns one Answer.value;
/api/v1/sparql returns rows. Test multi-valued pairs against SPARQL,
not against single-value /query.

Usage:
    python scripts/generate_scaled_facts.py --n-facts 2000 --n-entities 400
    python scripts/generate_scaled_facts.py --n-facts 2000 --n-entities 400 \
        --out configs/titanos-facts-2000.json
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


MAX_OBJS_PER_PAIR = 4


def generate(
    n_facts: int,
    n_entities: int,
    n_relations: int,
    multi_valued_frac: float,
    n_queries: int,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)

    if n_facts < 1:
        raise ValueError("n_facts must be >= 1")
    if n_entities < 2:
        raise ValueError("n_entities must be >= 2 (need at least s != o)")
    if n_relations < 1:
        raise ValueError("n_relations must be >= 1")
    if not (0.0 <= multi_valued_frac <= 1.0):
        raise ValueError("multi_valued_frac must be in [0, 1]")

    max_possible = n_entities * n_relations * MAX_OBJS_PER_PAIR
    if n_facts > max_possible:
        raise ValueError(
            f"n_facts={n_facts} exceeds max possible ({max_possible} = "
            f"{n_entities} * {n_relations} * {MAX_OBJS_PER_PAIR})"
        )

    entity_names = [f"e_{i:04d}" for i in range(n_entities)]
    relation_names = [f"rel_{i:02d}" for i in range(n_relations)]

    pair_to_objs: dict[tuple[int, int], set[int]] = defaultdict(set)
    multi_pairs: set[tuple[int, int]] = set()
    facts: list[tuple[int, int, int]] = []

    max_iters = n_facts * 1000
    for _ in range(max_iters):
        if len(facts) >= n_facts:
            break
        s = int(rng.integers(n_entities))
        r = int(rng.integers(n_relations))
        pair = (s, r)

        current_objs = pair_to_objs[pair]
        if current_objs:
            if pair not in multi_pairs:
                continue
            if len(current_objs) >= MAX_OBJS_PER_PAIR:
                continue
        else:
            if rng.random() < multi_valued_frac:
                multi_pairs.add(pair)

        o = int(rng.integers(n_entities))
        if o == s or o in current_objs:
            continue

        pair_to_objs[pair].add(o)
        facts.append((s, r, o))

    if len(facts) < n_facts:
        raise RuntimeError(
            f"could only generate {len(facts)}/{n_facts} facts before "
            f"iteration cap. Increase n_entities or decrease "
            f"multi_valued_frac."
        )

    # Actual distribution (from data, not design intent)
    n_multi_valued_pairs_actual = sum(
        1 for objs in pair_to_objs.values() if len(objs) >= 2
    )
    n_single_valued_pairs_actual = sum(
        1 for objs in pair_to_objs.values() if len(objs) == 1
    )

    # Build query set
    single_valued_pairs = [
        p for p, objs in pair_to_objs.items() if len(objs) == 1
    ]
    inverse_index: dict[tuple[int, int], list[int]] = defaultdict(list)
    for s, r, o in facts:
        inverse_index[(o, r)].append(s)
    single_inverse = [k for k, v in inverse_index.items() if len(v) == 1]

    n_forward = n_queries // 2
    n_inverse = n_queries - n_forward

    rng.shuffle(single_valued_pairs)
    rng.shuffle(single_inverse)

    queries = []
    for i in range(min(n_forward, len(single_valued_pairs))):
        s, r = single_valued_pairs[i]
        o = next(iter(pair_to_objs[(s, r)]))
        queries.append({
            "subject": entity_names[s],
            "relation": relation_names[r],
            "expected": entity_names[o],
            "inverse": False,
        })

    for i in range(min(n_inverse, len(single_inverse))):
        o, r = single_inverse[i]
        s = inverse_index[(o, r)][0]
        queries.append({
            "subject": entity_names[o],
            "relation": relation_names[r],
            "expected": entity_names[s],
            "inverse": True,
        })

    return {
        "metadata": {
            "generated_by": "scripts/generate_scaled_facts.py",
            "seed": seed,
            "n_facts": len(facts),
            "n_entities": n_entities,
            "n_relations": n_relations,
            "multi_valued_frac_target": multi_valued_frac,
            "n_multi_valued_pairs_actual": n_multi_valued_pairs_actual,
            "n_single_valued_pairs_actual": n_single_valued_pairs_actual,
            "n_queries": len(queries),
        },
        "entities": entity_names,
        "relations": relation_names,
        "facts": [
            [entity_names[s], relation_names[r], entity_names[o]]
            for s, r, o in facts
        ],
        "queries": queries,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate a synthetic facts config at a target size."
    )
    ap.add_argument("--n-facts", type=int, default=2000)
    ap.add_argument("--n-entities", type=int, default=400)
    ap.add_argument("--n-relations", type=int, default=20)
    ap.add_argument("--multi-valued-frac", type=float, default=0.4)
    ap.add_argument("--n-queries", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--out", type=str, default="configs/titanos-facts-scaled.json"
    )
    args = ap.parse_args()

    payload = generate(
        n_facts=args.n_facts,
        n_entities=args.n_entities,
        n_relations=args.n_relations,
        multi_valued_frac=args.multi_valued_frac,
        n_queries=args.n_queries,
        seed=args.seed,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")

    meta = payload["metadata"]
    total_pairs = (
        meta["n_multi_valued_pairs_actual"]
        + meta["n_single_valued_pairs_actual"]
    )
    print(f"facts:               {meta['n_facts']}")
    print(f"entities:            {meta['n_entities']}")
    print(f"relations:           {meta['n_relations']}")
    print(
        f"multi-valued pairs:  {meta['n_multi_valued_pairs_actual']} "
        f"({meta['n_multi_valued_pairs_actual'] / max(total_pairs, 1):.1%})"
    )
    print(f"single-valued pairs: {meta['n_single_valued_pairs_actual']}")
    print(f"queries:             {meta['n_queries']}")
    print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
