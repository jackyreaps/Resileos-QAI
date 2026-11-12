---
doc: BENCH-2026-11-12
title: Measurement sample, 2026-11-12
status: measured
---

# Measurement sample, 2026-11-12

This note records one run on a cursor cloud agent VM. It covers exact recall, abstention, chain composition, equal-budget hierarchy checks, temporal conflict, in-process ask/chain latency, and the mouth-policy leak count.

It does not score generation, fluent coding, or general reasoning. No language model was called. Nothing here says the system is ahead of a model on an unmeasured task.

Machine: Linux 6.12.113+, x86_64, Python 3.12.3, 4 CPUs, `/proc/cpuinfo` model string `Intel(R) Xeon(R) Processor`. Latency will move if the run is repeated. The JSON files hold the full floats. Tables below round milliseconds to 3 decimal places except where the script already rounded to 1.

Index: `landing/artifacts/report_measurement_2026-11-12.json`.

## Exact recall and abstention

`scripts/ops/bench_vs_llm.py` on the same 3 known facts and 12 unknown pairs. Backend `titanos`, not the dict stub. `BENCH_LLM_URL` and `BENCH_LLM_KEY` were unset, so the LLM rates are null.

Artifact: `landing/artifacts/report_memory_vs_llm_2026-11-12.json`.

| Metric | Resileos | LLM |
|---|---:|---|
| Exact match on 3 known facts | 1.0 | not run |
| Invent rate on 12 unknown pairs | 0.0 | not run |
| Abstain rate on those 12 | 1.0 | not run |
| p50 of the 3 known queries | 111.771 ms | not run |
| Mean of those 3 queries | 115.585 ms | not run |

The p50 is the middle of the three query times, not the batch time divided by 3. A 2026-11-10 run on another machine reported a lower p50. That number is not this sample.

## Composition

In-process `Titanos.ask`, `ask_inverse`, and `chain` on the three compositions in `scripts/ops/bench_compositional.py`. No HTTP server was listening, so the HTTP leg was skipped. No model key was set.

Artifact: `landing/artifacts/report_compositional_2026-11-12.json`.

| Question | Expected | Got | ms |
|---|---|---|---:|
| Who is alice's grandchild? | carol | carol | 240.2 |
| Who is carol's grandparent? | alice | alice | 222.5 |
| Where does carol's parent work? | globex | globex | 222.5 |

Composition rate 1.0 (3/3). These hops are exact lookups. They are not a measure of open-ended planning.

## Equal budget and residual consistency

`scripts/bench/equal_budget.py`, 22 tasks, step budget 8. Both paths scored 22/22, correct-abstain 6/6, false accepts 0. The hierarchy path did not add a fact the lookup did not already return.

Artifact: `landing/artifacts/report_equal_budget_2026-11-12.json`.

| Metric | Residual / Apollo | Kin + Demi-gods + Hades |
|---|---:|---:|
| Accuracy | 1.0 (22/22) | 1.0 (22/22) |
| Correct-abstain rate | 1.0 (6/6) | 1.0 (6/6) |
| False accepts | 0 | 0 |
| Steps, mean | 1.0 | 6.0 |
| Steps, max | 1 | 6 |
| Latency, mean | 0.388 ms | 32.821 ms |
| Latency, total | 8.539 ms | 722.062 ms |
| Cycle residual-consistency true | — | 22/22 |
| Cycle `verified` true | — | 0/22 |

On all 22 hierarchy cycles the harness reason was `no evidence attached`. That call passes metrics only, and `kin_cycle` requires evidence before `verified` becomes true. Consistency was true. Verification was not. This run does not change the call. The answer still came from the shared lookup, and the false-accept count stayed 0.

## Temporal conflict

`scripts/run_temporal_probe.py` on `configs/titanos-facts.json` (120 facts).

Artifact: `landing/artifacts/report_temporal_probe_2026-11-12.json`.

| Check | Result |
|---|---|
| Reference M9 | 0.0 (0/141), pass |
| Overlap moments with both objects | 2/2 |
| Non-overlap moments with one object | 2/2 |
| Probe pass | true |

## M5 latency

`scripts/bench/latency_m5.py`. 100 sequential in-process calls after one excluded warmup. Exact asks are single-valued pairs (66 distinct, cycled). Exact chains are two single-valued hops (41 distinct, cycled). Every timed call matched the stored object.

Artifact: `landing/artifacts/report_latency_m5_2026-11-12.json`.

| Call | Exact | p50 ms | p95 ms | p99 ms | p95 < 500ms |
|---|---:|---:|---:|---:|---|
| `ask` | 100/100 | 164.293 | 254.575 | 280.985 | yes |
| `chain` | 100/100 | 495.692 | 543.971 | 644.048 | no |

The capacity target is p95 under 500ms. Ask met it on this sample. Chain did not. These are method calls on this VM, not HTTP.

## M7 mouth-policy leak

`scripts/bench/mouth_leak.py`. `require_verified` default stayed true. Pytest asserts `leak_count == 0`.

Artifact: `landing/artifacts/report_mouth_leak_2026-11-12.json`.

| Count | Result | In `leak_count` |
|---|---:|---|
| Policy opened on an unverified harness | 0 / 6 | yes |
| Factual prose while `verified` is false | 0 / 2400 | yes |
| Planted object in non-preference text | 0 / 2400 | yes |
| `leak_count` | 0 | target 0 |
| Non-empty template text | 1704 / 2400 | no |
| Preference topic echoed | 480 / 2400 | no |

The policy gate did not authorize prose for an unverified cycle. `render_persona_mouth` still returns orientation, abstain, and preference template text on some unverified turns. Those templates did not contain the planted store object, and `factual` stayed false. Counting every non-empty string would not be 0. The mouth was not changed.

## Skipped

- LLM baseline. Both `BENCH_LLM_URL` and `BENCH_LLM_KEY` were unset. Rates were not filled in.
- Composition and M5 over HTTP. Nothing was listening, and this run did not start the API.
- M6, the 5k-fact corpus. `scripts/generate_scaled_facts.py` can build one. This run did not generate it, seed it, or commit a fixture. M6 is unmeasured.
- M8 hub concurrency. Not part of this run.
- Invention bench. Not re-run. The 2026-11-10 note still stands for that script only.

## Reproduce

From the repo root:

```bash
PYTHONPATH=src:scripts python scripts/ops/publish_measurements.py
```

That command rewrites the dated JSON under `landing/artifacts/`. A second run will not match these latencies exactly.
