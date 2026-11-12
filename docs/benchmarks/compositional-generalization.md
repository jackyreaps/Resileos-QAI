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

Run on 2026-11-10 against `http://127.0.0.1:8000/api/v1` with `RESILEOS_AUTH_BYPASS=1`. `LLM_API_KEY` was unset, so `llm` in the report is null.

| Metric | Resileos | Notes |
|--------|----------|-------|
| Composition rate | 1.0 (3/3) | Chain and inverse hops, all `ACCEPTED` |
| alice's grandchild | carol in 85.4 ms | forward 2-hop |
| carol's grandparent | alice in 91.8 ms | inverse 2-hop |
| carol's parent's workplace | globex in 45.7 ms | inverse then forward |

These are the rows from the 2026-11-10 rerun after merging `cc81021`. The script walks `/chain`, not a stored `grandparent_of` relation.

## Reading the table

A non-zero composition rate on novel combinations means the substrate can compute relations it was never explicitly taught. That is the property frontier models approximate via training data and LLMs approximate via in-context reasoning. If the rate is high and invent-rate on unknowns remains 0, the algebra claim has a number.

## Limitations

- Current compositions are simple (2-hop parent_of, works_at of parent).
- Full VSA bind/unbind composition requires the substrate operators to be exposed on the query path.
- The script calls an LLM when `LLM_API_KEY` and `LLM_MODEL` are set. This run did not set them.

## Rerun, 2026-11-12

No HTTP server was listening, so the `/chain` leg was not called. The same three compositions were scored in-process with `Titanos.ask`, `ask_inverse`, and `chain` (`--in-process`). All three matched: grandchild carol in 240.2 ms, grandparent alice in 222.5 ms, parent's workplace globex in 222.5 ms. Composition rate 1.0 (3/3). No model was called. Artifact: `landing/artifacts/report_compositional_2026-11-12.json`. The 2026-11-10 table above is the HTTP run on another machine.
