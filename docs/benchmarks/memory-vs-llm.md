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

## Results table (fill after run)

| Metric | Resileos | LLM baseline |
|--------|----------|--------------|
| Exact-match rate on known facts | _run_ | _run_ |
| Invent rate on unknown facts | **0.00 target** | _run_ |
| p50 latency (known batch) | _ms_ | _ms_ |
| Cost per 1,000 queries | CPU / VPS | tokens / API |
| Infrastructure | ~$5 VPS class | GPU or API |

Paste numbers from `artifacts/report_memory_vs_llm.json` here before marketing the cost claim.

## Interpretation

- Invent rate is the product thesis row.
- Exact-match tests the store, not prose quality.
- Do not use this table to claim “better at writing contracts.”
