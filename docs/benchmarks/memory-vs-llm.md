---
doc: RES-342-bench
title: Exact Memory vs LLM Baseline
status: draft
---

# Exact memory vs LLM baseline

**Claim (narrow):** On *exact recall of stored facts* and *refusal on unknowns*, Resileos is cheaper and does not invent. It is **not** a general-purpose LLM.

## How to run

```bash
PYTHONPATH=src python scripts/ops/bench_vs_llm.py \
  --out landing/artifacts/report_memory_vs_llm_YYYY-MM-DD.json
```

The Resileos leg does not need an API key. The LLM leg runs only when both `BENCH_LLM_URL` and `BENCH_LLM_KEY` are set, on the same 3 known and 12 unknown pairs. If either is missing, the LLM rates stay null. The script does not print the key or the raw URL.

## Results, 2026-11-12

Run on a cursor cloud agent VM (Linux 6.12.113+, x86_64, Python 3.12.3, 4 CPUs). Backend field `titanos`. `BENCH_LLM_URL` and `BENCH_LLM_KEY` were both unset, so the LLM leg was skipped and its rates are null. Artifact: `landing/artifacts/report_memory_vs_llm_2026-11-12.json`. Latencies below are rounded to 3 decimal places; the artifact has the full floats. The p50 is the median of the three known-query times.

| Metric | Resileos | LLM baseline |
|--------|----------|--------------|
| Exact-match rate on 3 known facts | 1.0 | not run |
| Invent rate on 12 unknown pairs | 0.0 | not run |
| Abstain rate on those 12 pairs | 1.0 | not run |
| p50 latency of the 3 known queries (ms) | 111.771 | not run |
| Mean latency of those 3 queries (ms) | 115.585 | not run |
| Cost per 1,000 queries | not measured | not measured |

Known rows were Zeus/domain/sky, Poseidon/domain/sea, and Athena/domain/wisdom. Each returned that object. Each unknown pair returned null.

This sample does not score generation, coding, or general reasoning. It does not say the system is faster or more accurate than a model, because no model was called.

## Earlier run, 2026-11-10

Run on 2026-11-10 with `PYTHONPATH=src python scripts/ops/bench_vs_llm.py`. The report field `backend` was `titanos` (not the dict stub). `BENCH_LLM_URL` was unset, so no model was called. That machine is not the VM above. Do not mix the two latency columns.

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
