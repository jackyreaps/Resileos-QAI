doc: RES-000
title: Documentation Index
status: stable
depends_on: []
referenced_by: [RES-100]

# Resileos-QAI Documentation

**Version:** see [`/version`](../version) · **Changelog:** [`/changelog.md`](../changelog.md)

**Status vocabulary.** `draft`, `stable`, `deprecated`, `conditional`,
`conjectural`, `candidate`, `proposal`, `heuristic`.

## Reading order

Foundations:
1. [Overview](100-foundations/overview.md) — RES-100
2. [Architecture](100-foundations/architecture.md) — RES-101
3. [Design Principles](100-foundations/design-principles.md) — RES-102

Classical core:
4. [Classical Core](200-core/classical-core.md) — RES-200
5. [Control Packet](200-core/control-packet.md) — RES-201
6. [Canonicalization](200-core/canonicalization.md) — RES-202

Substrate:
7. [HDRIFT Adapter](300-substrate/hdrift-adapter.md) — RES-300
8. [Moment Bundle](300-substrate/moment-bundle.md) — RES-301
9. [Abstention](300-substrate/abstention.md) — RES-302
10. [Sigma Gate](300-substrate/sigma-gate.md) — RES-303
11. [Structure-Flux-Mode Triad](300-substrate/triad.md) — RES-304
12. [Causal Sandbox Index](300-substrate/causal-sandbox.md) — RES-305
13. [Phasor Graph](300-substrate/phasor-graph.md) — RES-306
14. [Agency Hierarchy](300-substrate/agency-hierarchy.md) — RES-307
15. [Constructive Head](300-substrate/constructive-head.md) — RES-308
16. [Entanglement Pipeline Engine](300-substrate/entanglement-pipeline.md) — RES-309
17. [Order Parameter Gate](300-substrate/order-parameter-gate.md) — RES-316
18. [SDM + Hopfield Attractor Memory](300-substrate/sdm-hopfield.md) — RES-317
19. [Engine Group Composition](300-substrate/engine-group.md) — RES-318
20. [Engine Group Signal Probe Results](300-substrate/engine-group-results.md) — RES-319
21. [Path B Mechanism Confirmation](300-substrate/pathb-mechanism.md) — RES-326

Hierarchy / modulation:
22. [Hierarchical Encoding](310-hierarchy/hierarchical-encoding.md) — RES-310
23. [Streaming Substrate State](310-hierarchy/streaming-state.md) — RES-311
24. [Layered Mask Stack](310-hierarchy/mask-stack.md) — RES-312
25. [Composition Capacity Law](310-hierarchy/capacity-law.md) — RES-313
26. [Error Accumulation Bound](310-hierarchy/error-bound.md) — RES-314
27. [Modulation Interface](310-hierarchy/modulation-interface.md) — RES-315

Titanos application layer:
28. [Disk-Backed Band Store](320-titanos/store.md) — RES-320
29. [Dense Entity Index](320-titanos/index.md) — RES-321
30. [Query Language and Execution](320-titanos/query.md) — RES-322
31. [External Ingestion](320-titanos/ingestion.md) — RES-323
32. [Zeus Child](320-titanos/zeus-child.md) — RES-324
33. [Eat Strategy](320-titanos/eat-strategy.md) — RES-325
34. [Answer Route and Pluggable Backends](320-titanos/answer.md) — RES-327
35. [Temporal Semantics](320-titanos/temporal.md) — RES-332

Operations:
36. [Capacity Contract](400-operations/capacity-contract.md) — RES-330
37. [Capacity Acceptance Results](400-operations/capacity-results.md) — RES-331
38. [Run Config](400-operations/run-config.md) — RES-400
39. [phi-compress redesign](400-operations/phi-compress-redesign.md) — RES-401

Notes and roadmap:
40. [Behavioral Notes](500-notes/behavioral.md) — RES-500
41. [Roadmap](500-notes/roadmap.md) — RES-501
42. [Hardened Roadmap](500-notes/hardened-roadmap.md) — RES-502

QD-TER bridge:
43. [FEP Reduction Bridge](600-qdter/fep-reduction.md) — RES-600
44. [Non-Dual Adaptation Layer](600-qdter/non-dual-adaptation.md) — RES-601
45. [Two-Head Integration Note](600-qdter/integration.md) — RES-602
46. [Speculative Cross-Stream](600-qdter/speculative-cross-stream.md) — RES-603
47. [QD-TER Bridge Status](600-qdter/status.md) — RES-604
48. [leCore Integration Bridge](600-qdter/lecore-bridge.md) — RES-605
49. [Metric Bridge Candidate Derivations](600-qdter/metric-bridge-derivations.md) — RES-606
50. [Spectral Skeleton](600-qdter/spectral-skeleton.md) — RES-607
51. [leCore as Stomach](600-qdter/lecore-stomach.md) — RES-608

Harness and current product surface (code on main; some numbered docs above still say draft or deferred):
- [`docs/harness/AGENTS.md`](harness/AGENTS.md) — standing instructions
- [`docs/harness/CONSTRAINTS.md`](harness/CONSTRAINTS.md) — permanent corrections
- [`docs/harness/INTEGRATION.md`](harness/INTEGRATION.md) — integration checklist
- [Demi-god skill layer](320-titanos/demigods.md) — RES-343, implemented
- [Legions under Kin](320-titanos/legions.md) — RES-345, registration implemented; examples off unless enabled
- [Kin operators and eat](320-titanos/kin-eat-build.md) — RES-338, implemented
- [Aphrodite](320-titanos/aphrodite.md) — preferences and tutorial steps; no residual writes
- [Persona store](320-titanos/persona-store.md) — individual, guild hub, and latent tiers for the tutorial mouth
- [Hermes coordination](320-titanos/hermes-coordination.md) — Clotho, Lachesis, Atropos, Harmonia
- [Verifier swarm](320-titanos/verifier-swarm.md) — RES-340, implemented
- [Equal-budget measurement](benchmarks/equal_budget.md) — RES-344, measured 2026-11-10
- [Studio residual codec study](studio/research.md) — STUDIO-001
- [External samplers and the MiniMax-H3-Image license](studio/external-samplers.md) — STUDIO-002
- [Exact memory bench](benchmarks/memory-vs-llm.md), [chain composition](benchmarks/compositional-generalization.md), [invention bench](benchmarks/invention-without-hallucination.md) — 2026-11-10 runs; no model key was set
- [Measurement sample, 2026-11-12](benchmarks/measurement-2026-11-12.md) — exact recall, abstention, composition, equal budget, temporal conflict, in-process latency, mouth-policy leak count. No model was called. Chain p95 on that VM was above 500 ms.
- [Component inventory](320-titanos/component-inventory.md) — RES-346. What Kin, demi-gods, legions, swarms, and studio modules do on this tree, and which shells were left alone.
- [Cascade address](200-core/cascade-address.md) — Human Belt, pins, and orientation scales on frames (3, 5, 9, 12)
- [Oscillator depth](300-substrate/oscillator-depth.md) — Kuramoto field depth and outward weight
- [Outer layer](320-titanos/outer-layer.md) — Hermes envelopes → Eat → Zeus reviewers → Titanos
- [Cascade promotion](320-titanos/tier-promotion.md) — one-step, opt-in subject for a verified fact
- [Guild merit](320-titanos/guild-merit.md) — merit and credit in a guild

Reference:
52. [Glossary](900-reference/glossary.md) — RES-900

## Categories

| Range | Category | Entry point |
|---|---|---|
| 100 | Foundations | [Overview](100-foundations/overview.md) |
| 200 | Classical Core | [Classical Core](200-core/classical-core.md) |
| 300 | Generative Substrate | [HDRIFT Adapter](300-substrate/hdrift-adapter.md) |
| 310 | Hierarchy / Modulation | [Hierarchical Encoding](310-hierarchy/hierarchical-encoding.md) |
| 320 | Titanos Application Layer | [Disk-Backed Band Store](320-titanos/store.md) |
| 400 | Operations | [Capacity Contract](400-operations/capacity-contract.md) |
| 500 | Notes & Roadmap | [Roadmap](500-notes/roadmap.md) |
| 600 | QD-TER Bridge | [Status](600-qdter/status.md) |
| 900 | Reference | [Glossary](900-reference/glossary.md) |

## 320-series Titanos modules

| Doc | Module | Status | Notes |
|---|---|---|---|
| RES-320 | `store.py` | stable | Memory-mapped int32 accumulators + WAL |
| RES-321 | `index.py` | stable | Bidirectional name ↔ id ↔ vector index |
| RES-322 | `query.py` | draft | SPARQL-like grammar and nested-loop executor |
| RES-323 | `ingest.py` | draft | External ingestion; φ-ladder, R-gate, filter |
| RES-324 | `zeus-child.md` | draft | AgencyChild residual specialist; declines when unfit |
| RES-325 | `eat-strategy.md` | draft | Eat strategy. Read the doc for its own limits. |
| RES-327 | `answer.md` | stable | `/answer` route; pluggable backends; RAG scaling measured |
| RES-332 | `temporal.md` | draft | Doc status is draft. `scripts/titanos.py` implements `valid_from` / `valid_to` and `as_of`. The probe reports reference M9 0/141. |
| RES-338 | `kin-eat-build.md` | implemented | Iris, Metis, Hermes, Eat |
| RES-340 | `verifier-swarm.md` | implemented | Deterministic checkers used by `SeparatedCycle` |
| RES-343 | `demigods.md` | implemented | Themis, Momus, Hephaestus, Nike, Atlas: summon, one check, dismiss |
| RES-345 | `legions.md` | implemented | `register_legion`; examples off unless `enable=True` |

## 400-series operations modules

| Doc | Module | Status | Notes |
|---|---|---|---|
| RES-330 | `capacity-contract.md` | proposed | Capacity rules C0–C8; metrics M1–M9 |
| RES-331 | `capacity-results.md` | stable | M1–M4 pass on 2026-11-03. A 2026-11-12 sample measured M5, M7, and M9 (chain p95 on that VM was above 500 ms). M6 and M8 were not measured. Reference M9 on that sample was 0/141. |
| RES-401 | `phi-compress-redesign.md` | draft | Golden-ladder contraction under R-gating |

## 600-series QD-TER bridge

| Doc | Title | Status |
|---|---|---|
| RES-600 | FEP Reduction Bridge | conditional |
| RES-601 | Non-Dual Adaptation Layer | conjectural |
| RES-602 | Two-Head Integration Note | draft |
| RES-603 | Speculative Cross-Stream | draft |
| RES-604 | QD-TER Bridge Status | stable |
| RES-605 | leCore Integration Bridge | stable |
| RES-606 | Metric Bridge Candidate Derivations | candidate |
| RES-607 | Spectral Skeleton | conjectural |
| RES-608 | leCore as Stomach | draft |

The status page (RES-604) is the canonical open/closed inventory.

## Dependency graph

```text
RES-100 ─▶ RES-101 ─▶ RES-102
    │
    ▼
RES-200 ─▶ RES-201 ─▶ RES-202
    │
    ▼
RES-300 ─▶ RES-301 ─▶ RES-302 ─▶ RES-303
    │
    ▼
RES-304 ─▶ RES-318 ─▶ RES-319 ─▶ RES-326
RES-305  RES-306 ─▶ RES-307
    │
    ├──▶ RES-308
    └──▶ RES-309
    │
    ▼
RES-310 ─▶ RES-311 ─▶ RES-312
    │         │         │
    └────┬────┴────┬────┘
         ▼         ▼
    RES-313 ─▶ RES-314
         │         │
         └────┬────┘
              ▼
         RES-315
    │
    ▼
RES-316 ─▶ RES-317
    │
    ▼
RES-320 ─▶ RES-321 ─▶ RES-322 ─▶ RES-323
                                    │
                                    ├──▶ RES-324
                                    ├──▶ RES-325
                                    ├──▶ RES-327
                                    └──▶ RES-332
    │
    ▼
RES-330 ─▶ RES-331 ─▶ RES-401
    │
    ▼
RES-400 ─▶ RES-500 ─▶ RES-501 ─▶ RES-502
    │
    ▼
RES-600 ─▶ RES-601 ─▶ RES-602 ─▶ RES-603
                                    │
                                    ▼
                               RES-604 ─▶ RES-605 ─▶ RES-606
                                                          │
                                                          ▼
                                                     RES-607 ─▶ RES-608
```
