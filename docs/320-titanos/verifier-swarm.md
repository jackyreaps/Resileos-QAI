---
doc: RES-340-verifier-swarm
title: Deterministic Verifier Swarm
status: implemented
depends_on: [RES-338-kin-eat]
related_to: [frame-atlas-bridge]
---

# Verifier Swarm

## Role

Multi-stage **deterministic** gate before `learn`. Not a swarm of LLMs.

Pipeline: schema → sys_guard → relation_token → size → contradiction → provenance → temporal → capacity → hub_consistency.

## Frames (dimensionality tags)

Operational tags on `VerifierReport.frame` / `EatDecision.frame`:

| Tag | Meaning |
|-----|---------|
| `exact` | Accepted structured truth |
| `provisional` | Accepted without strong provenance |
| `filtered` | Rejected by a checker |
| `abstained` | Unstructured / unresolved |

These are **gate categories**, not a claim of cognitive consciousness. They align with answer honesty frames (`exact|abstained|…`) so Studio and API can surface dimensionality of a decision without inventing content.

## Code

`src/resileos/kin/verifiers.py` · integrated via `eat_filter(..., use_swarm=True)`.

## Benchmark

`scripts/ops/bench_vs_llm.py` → invent rate row is the product thesis.
