---
doc: BENCH-003
title: Invention Without Hallucination
status: draft — candidate tier not implemented on the query path
depends_on: [BENCH-002, kin-eat]
referenced_by: [MKT-001]
---

# Invention Without Hallucination

**Current status.** The candidate tier is **not** implemented on
`POST /api/v1/query`. The API returns `ACCEPTED`, `ABSTAINED`,
`NONE_CHANNEL`, or `NO_ROWS`. It does not return `CANDIDATE` or
`PROVISIONAL`.

What is live today:

| Behavior | Status |
|---|---|
| Stored facts returned exactly | Live |
| Chain / derivation with provenance | Live |
| Unknown relations abstain | Live |
| Novel compositions marked as candidates | **Not live** |

**The claim that is currently true.** On unknown relations the system
abstains rather than inventing. An LLM baseline given the same facts
still invents on some fraction of unknowns. That is the invent-rate row
in `memory-vs-llm.md`.

**The claim that is not yet true.** “Novel compositions are marked as
candidates, never asserted as facts.” That requires a status the API
does not return. Do not describe the candidate tier as working until
`/query` or a dedicated route returns it.

## What the benchmark measures today

Run `scripts/ops/bench_invention.py` against a live API. Until a
candidate status exists, interpret the output as:

- derivation_rate — chain works or it does not
- novelty_rate — expected near 0 (nothing invented)
- assertion_rate_on_novel — expected 0 (abstention, not marking)

That table is honest. It is the abstention claim, not the invention
claim.

## What would make the candidate tier real

A response field or status (`CANDIDATE` / `PROVISIONAL`) on a route that
emits novel compositions, with the verifier gate still between that
status and durable `learn()`. Until that exists, keep this document
aligned with the README: candidate tier is not built.
