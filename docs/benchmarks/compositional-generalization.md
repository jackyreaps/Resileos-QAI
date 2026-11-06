---
doc: BENCH-002
title: Compositional Generalization
status: draft
depends_on: [RES-330, kin-eat]
---

# Compositional Generalization

**What this measures.** Given a set of base facts, can the system answer novel combinations of those relations without having stored the composed fact explicitly.

Example corpus:
- alice parent_of bob
- bob parent_of carol

Query: carol grandparent_of → alice

**What this does not measure.** Open-ended reasoning, multi-hop planning beyond simple composition, or generation.

## Reproduce

```bash
export RESILEOS_API_KEY=...
export RESILEOS_BASE_URL=http://127.0.0.1:8000/api/v1
python scripts/ops/bench_compositional.py
```

## Results

| Metric | Resileos | Notes |
|--------|----------|-------|
| Composition rate (novel queries) | _run_ | Algebraic / chain |
| Latency p50 (composed queries) | _ms_ | |

*(Populate from `artifacts/report_compositional.json` after a host run.)*

## Reading the table

A non-zero composition rate on novel combinations means the substrate can compute relations it was never explicitly taught. That is the property frontier models approximate via training data and LLMs approximate via in-context reasoning. If the rate is high and invent-rate on unknowns remains 0, the algebra claim has a number.

## Limitations

- Current compositions are simple (2-hop parent_of, works_at of parent).
- Full VSA bind/unbind composition requires the substrate operators to be exposed on the query path.
- LLM baseline is not yet wired in this script; add it once the Resileos number exists.
