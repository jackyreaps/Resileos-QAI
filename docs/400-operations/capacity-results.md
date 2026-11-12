doc: RES-331
title: Capacity Acceptance Results
status: stable
depends_on: [RES-330, RES-327, RES-332]
referenced_by: [RES-501]

# Capacity Acceptance Results

RES-330 (capacity-contract.md) defines nine operating metrics M1-M9
with target bounds. This document records the acceptance run: M1-M4
measured and passing; M5-M9 specified but not yet measured, each
documented with what it measures, why deferred, and how to measure it.

## 0. Status

First acceptance run: 2026-11-03. M1-M4 pass. M5-M9 were deferred then.

A later sample on 2026-11-12, on a cursor cloud agent VM, measured M5
(in-process ask and chain), M7 (mouth-policy leak count), and M9
(temporal probe). M6 and M8 were not measured. Chain p95 on that VM
was above the 500ms target. Details are in the subsections below.

## 1. What was measured

| Metric | Target | Measured | Pass |
|---|---|---|---|
| M1 honesty | 1.0 | 1.0 | yes |
| M2 invent | 0.0 | 0.0 | yes |
| M3 store hit | >= min_probe_hit_rate | 1.0 | yes |
| M4 hub reload (in-process) | 1.0 | 1.0 | yes |

Definitions from RES-330 §3:

- **M1 honesty** — fraction of tool calls whose schema exactly matches
  the declared tool spec. 1.0 = every call well-formed.
- **M2 invent** — fraction of returned entities not present in the
  store. 0.0 = no fabricated entities.
- **M3 store hit** — fraction of queries resolved from the store
  without fallback to the model. 1.0 = every query answered from
  stored facts.
- **M4 hub reload** — fraction of state preserved across a hub process
  restart. 1.0 = no data lost.

## 2. Interpretation

M1 = 1.0 is the strongest signal. Every tool call conformed to the
schema; no malformed calls. The honesty contract at its ceiling.

M2 = 0.0 is the second-strongest. Zero hallucinated entities across
the corpus. Combined with M1, the model never produced an output that
was both malformed and fabricated.

M3 = 1.0 means the store answered every query. The "store is the
truth engine" claim, measured rather than asserted.

M4 = 1.0 means the hub survives reload. Docker strict also passes; see §5.

## 3. What is not measured

### M5 — latency

**Target:** p95 query latency < 500ms at the reference corpus.

**Measured 2026-11-12** with `scripts/bench/latency_m5.py` on a cursor
cloud agent VM: Linux 6.12.113+, x86_64, Python 3.12.3, 4 CPUs, CPU
model string `Intel(R) Xeon(R) Processor` from `/proc/cpuinfo`. The
store was a fresh `Titanos(TitanosConfig())` seeded with the 120 facts
in `configs/titanos-facts.json`. One untimed warmup call per operation
was excluded. The next 100 calls were timed. No HTTP server was
started, so these are in-process method times, not socket round trips.
Percentiles use linear interpolation (p50 of 100 samples is the
midpoint of sorted indexes 49 and 50). Full floats are in
`landing/artifacts/report_latency_m5_2026-11-12.json`.

| Call | Exact accepts | Distinct queries | p50 ms | p95 ms | p99 ms | p95 < 500ms |
|---|---:|---:|---:|---:|---:|---|
| `ask` | 100/100 | 66 single-valued pairs | 164.293 | 254.575 | 280.985 | yes |
| `chain` | 100/100 | 41 two-hop paths | 495.692 | 543.971 | 644.048 | no |

An exact ask is a subject/relation with one stored object. An exact
chain is two hops that are each single-valued. Every timed call
returned that object (`exact_rate` 1.0). Ask met the 500ms p95 target
on this sample. Chain did not. This is one VM sample, not a hosted
API latency.

### M6 — scale

**Target:** M3 store hit >= 0.95 at 5,000 facts.

**Why deferred:** requires a 5k-fact corpus.
`scripts/generate_scaled_facts.py` exists; the corpus has not been
generated. The 2026-11-12 measurement run did not generate or seed
that corpus. M6 is still unmeasured.

**To measure:** generate 5k facts, seed, run M3 harness against the
same 120-fact query set, compare.

### M7 — chat-leak

**Target:** 0.0. No unverified writer output reaches the prose mouth.
`require_verified=True` remains the default of `should_render_prose`.

**Measured 2026-11-12** by `scripts/bench/mouth_leak.py`. Pytest runs
the same function and asserts `leak_count == 0`. Artifact:
`landing/artifacts/report_mouth_leak_2026-11-12.json`.

`leak_count` is policy authorizations on an unverified cycle, plus
factual prose while `verified` is false, plus spoken text that
contains a planted object outside a preference echo. That count was
**0**. The default of `require_verified` was true. Six injected
unverified harnesses, including a raised cycle and a missing harness,
did not open the policy. A verified control harness did open, so the
probe was reading the flag. Across 2400 `render_persona_mouth` calls
with `verified=False`, factual prose was 0 and the planted object
appeared in 0 non-preference lines.

The same sweep returned non-empty template text on **1704** calls
(orientation and abstain lines) and echoed the preference topic on
**480** calls. Those strings are not in `leak_count`. A reading that
counts every non-empty string as prose does not meet a target of 0.
This run does not change the mouth to silence those templates.

### M8 — hub concurrency

**Target:** no hub state corruption under N=4 concurrent writers.

**Why deferred:** `Hades` checkpoint landed 2026-11-09. A
concurrent-writer harness has not been built.

**To measure:** spawn 4 writer processes, each issuing `learn` to the
same subject, verify final state matches expected merge or
`council_query` reports `CONFLICT`.

### M9 — temporal conflict

**Target:** 0.0 on the reference corpus at any declared as_of. > 0.0
on synthetic overlap by construction, with every overlap surfacing as
`CONFLICT` not silent overwrite.

**Measured 2026-11-12** with `scripts/run_temporal_probe.py` on
`configs/titanos-facts.json` (120 facts). Artifact:
`landing/artifacts/report_temporal_probe_2026-11-12.json`.

| Check | Result |
|---|---|
| Reference M9 | 0.0 (0 conflicts / 141 checks), pass |
| Synthetic overlap | 2/2 overlap moments returned both objects |
| Non-overlap singular | 2/2 |
| Probe pass | true |

The reference set stayed single-valued at the three as_of moments the
probe uses. The synthetic overlap was surfaced as two rows, not one
overwrite. The same script is the measurement described below.

**What the probe does:** seeds the 120-fact corpus with `(None, None)`
validity, checks every single-valued `(s, r)` at three as_of moments
(reference M9), then seeds two synthetic facts with overlapping
validity and checks that both surface during overlap and exactly one
surfaces outside it.

## 4. What this closes

**M1-M4 are within bounds** — first acceptance run passes.

**The store is the truth engine** — M3 = 1.0 on the 120-fact corpus.

**The hub survives reload** — M4 = 1.0 (in-process + Docker strict).

## 5. Docker strict M4

Production-container reload: state written to `/app/data/` volume,
container restarted, state read back. All facts, entities, relations,
permutation, query counters, agency weights preserved. Result 1.0.

## 6. What this does not close

**Scale beyond 120 facts.** M1-M4 are statements about a 120-fact
store. M6 is the metric that would address this.

**M5-M9.** See §3.

**Temporal conflict.** The 2026-11-12 probe reported reference M9
0/141, synthetic overlap 2/2, and non-overlap singular 2/2. See §3.

**Correctness on ambiguous or multi-hop queries.** M1-M4 measure
well-formedness, grounding, store resolution, and durability — not
whether the answer was correct.

## 7. Reproduce

Measurement corpus: 120 facts from `configs/titanos-facts.json`.

M1-M3: chat-router + tool-schema path in `asgi.py`.
M4: `docker compose up -d`, mutate via `/api/v1/learn`,
`docker compose restart`, verify `/api/v1/stats` matches pre-restart.
M9: `scripts/run_temporal_probe.py` (requires RES-332 applied).

## 8. Read next

- [Capacity Contract](capacity-contract.md) — RES-330
- [Temporal Semantics](../320-titanos/temporal.md) — RES-332
- [Answer Route](../320-titanos/answer.md) — RES-327
- [Roadmap](../500-notes/roadmap.md) — RES-501
- [Documentation Index](../readme.md)
