---
doc: RES-342-bench
title: Exact Memory vs LLM Baseline
status: draft
---

# Exact memory vs LLM baseline

**Claim (narrow):** On *exact recall of stored facts* and *refusal on unknowns*, Resileos is cheaper and does not invent. It is **not** a general-purpose LLM.

## How to run

```bash
PYTHONPATH=src python scripts/ops/bench_vs_llm.py --out artifacts/report_memory_vs_llm.json
# optional LLM baseline:
# export BENCH_LLM_URL=...
# export BENCH_LLM_KEY=...
```

## Results table

Run on 2026-11-10 with `PYTHONPATH=src python scripts/ops/bench_vs_llm.py`. The report field `backend` was `titanos` (not the dict stub). `BENCH_LLM_URL` was unset, so no model was called.

| Metric | Resileos | LLM baseline |
|--------|----------|--------------|
| Exact-match rate on 3 known facts | 1.0 | not run |
| Invent rate on 12 unknown pairs | 0.0 | not run |
| p50 latency of the 3 known queries (ms) | 35.093815 | not run |
| Mean latency of those 3 queries (ms) | 35.693131 | not run |
| Cost per 1,000 queries | not measured | not measured |

The p50 is the median of the three per-query times. It is not the batch time divided by 3.

## Interpretation

- Invent rate is the product thesis row.
- Exact-match tests the store, not prose quality.
- Do not use this table to claim “better at writing contracts.”
