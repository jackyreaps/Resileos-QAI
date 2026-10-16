doc: RES-000
title: Documentation Index
status: stable
depends_on: []
referenced_by: [RES-100]

# Resileos-QAI Documentation

**Version:** see [`/version`](../version) · **Changelog:** [`/changelog.md`](../changelog.md)

**Status vocabulary.** Documents carry one of: `draft`, `stable`, `deprecated`,
`conditional`, `conjectural`, `candidate`, `proposal`, `heuristic`. The first
three are the original enum. The rest are extensions used by the 300-series and
600-series:

- `conditional` — true under stated assumptions
- `conjectural` — formal structure awaiting physical input
- `candidate` — a proposed derivation, not the canonical one
- `proposal` — a metric or design idea under test
- `heuristic` — operational parameters, not derived invariants

## Reading order

Foundations:
1. [Overview](100-foundations/overview.md) — RES-100
2. [Architecture](100-foundations/architecture.md) — RES-101
3. [Design Principles](100-foundations/design-principles.md) — RES-102

Classical core and substrate:
4. [Classical Core](200-core/classical-core.md) — RES-200
5. [Control Packet](200-core/control-packet.md) — RES-201
6. [Canonicalization](200-core/canonicalization.md) — RES-202
7. [HDRIFT Adapter](300-substrate/hdrift-adapter.md) — RES-300
8. [Moment Bundle](300-substrate/moment-bundle.md) — RES-301
9. [Abstention](300-substrate/abstention.md) — RES-302
10. [Sigma Gate](300-substrate/sigma-gate.md) — RES-303

Recent substrate extensions:
11. [Structure-Flux-Mode Triad](300-substrate/triad.md) — RES-304
12. [Causal Sandbox Index](300-substrate/causal-sandbox.md) — RES-305
13. [Phasor Graph](300-substrate/phasor-graph.md) — RES-306
14. [Agency Hierarchy](300-substrate/agency-hierarchy.md) — RES-307
15. [Constructive Head](300-substrate/constructive-head.md) — RES-308
16. [Entanglement Pipeline Engine](300-substrate/entanglement-pipeline.md) — RES-309

Hierarchy / modulation layer:
17. [Hierarchical Encoding](310-hierarchy/hierarchical-encoding.md) — RES-310
18. [Streaming Substrate State](310-hierarchy/streaming-state.md) — RES-311
19. [Layered Mask Stack](310-hierarchy/mask-stack.md) — RES-312
20. [Composition Capacity Law](310-hierarchy/capacity-law.md) — RES-313
21. [Error Accumulation Bound](310-hierarchy/error-bound.md) — RES-314
22. [Modulation Interface](310-hierarchy/modulation-interface.md) — RES-315

Titanos application layer:
23. [Disk-Backed Band Store](320-titanos/store.md) — RES-320
24. [Dense Entity Index](320-titanos/index.md) — RES-321
25. [Query Language and Execution](320-titanos/query.md) — RES-322

Operations and notes:
26. [Run Config](400-operations/run-config.md) — RES-400
27. [Training](400-operations/training.md) — RES-401
28. [Validation](400-operations/validation.md) — RES-402
29. [Behavioral Notes](500-notes/behavioral.md) — RES-500
30. [Roadmap](500-notes/roadmap.md) — RES-501

QD-TER bridge:
31. [FEP Reduction Bridge](600-qdter/fep-reduction.md) — RES-600
32. [Non-Dual Adaptation Layer](600-qdter/non-dual-adaptation.md) — RES-601
33. [Two-Head Integration Note](600-qdter/integration.md) — RES-602
34. [Speculative Cross-Stream](600-qdter/speculative-cross-stream.md) — RES-603
35. [QD-TER Bridge Status](600-qdter/status.md) — RES-604
36. [leCore Integration Bridge](600-qdter/lecore-bridge.md) — RES-605
37. [Metric Bridge Candidate Derivations](600-qdter/metric-bridge-derivations.md) — RES-606

Reference:
38. [Glossary](900-reference/glossary.md) — RES-900

## Categories

| Range | Category | Entry point |
|-------|----------|-------------|
| 100 | Foundations | [Overview](100-foundations/overview.md) |
| 200 | Classical Core | [Classical Core](200-core/classical-core.md) |
| 300 | Generative Substrate | [HDRIFT Adapter](300-substrate/hdrift-adapter.md) |
| 310 | Hierarchy / Modulation | [Hierarchical Encoding](310-hierarchy/hierarchical-encoding.md) |
| 320 | Titanos Application Layer | [Disk-Backed Band Store](320-titanos/store.md) |
| 400 | Operations | [Run Config](400-operations/run-config.md) |
| 500 | Notes & Roadmap | [Behavioral](500-notes/behavioral.md) |
| 600 | QD-TER Bridge | [Status](600-qdter/status.md) |
| 900 | Reference | [Glossary](900-reference/glossary.md) |

## 300-series substrate modules

| Doc | Module | Status | Notes |
|-----|--------|--------|-------|
| RES-304 | `triad.md` | draft | Structure-Flux-Mode triad |
| RES-305 | `sandbox.py` | proposal | Causal Sandbox Index; metric defined, not derived |
| RES-306 | `phasor.py` | stable | Phasor graph, band carriers, banded memory; Lean-backed |
| RES-307 | `agency.py` | heuristic | Routing layer; thresholds are operational parameters |
| RES-308 | `constructive-head.md` | proposal | Third head: drift direction from core dynamics; quantum-shaped only |
| RES-309 | `entanglement-pipeline.md` | conjectural | Shared-prefix structure as coarse-grained correlation; CHSH test proposed |

## 310-series hierarchy modules

| Doc | Module | Status | Notes |
|-----|--------|--------|-------|
| RES-310 | `hierarchical-encoding |.md` | draft | Tree of packets; capacity-driven levels |
| RES-311 | `streaming-state.md` | draft | Running stream_hv; decay and level weighting |
| RES-312 | `mask-stack.md` | draft | Layered masks; mask-to-sheath transition |
| RES-313 | `capacity-law.md` draft | Composition bound; trillion-token negative result |
| RES-314 | `error-bound.md` | draft | Empirical error model; redundancy contract |
| RES-315 | `modulation-interface.md` | draft | Carrier spec; what the modulation does |

## 320-series Titanos modules

| Doc | Module | Status | Notes |
|-----|--------|--------|-------|
| RES-320 | `store.py` | stable | Memory-mapped int32 accumulators + WAL |
| RES-321 | `index.py` | stable | Bidirectional name ↔ id ↔ vector index |
| RES-322 | `query.py` | draft | SPARQL-like grammar and nested-loop executor |

## 600-series QD-TER bridge

| Doc | Title | Status |
|-----|-------|--------|
| RES-600 | FEP Reduction Bridge | conditional |
| RES-601 | Non-Dual Adaptation Layer | conjectural |
| RES-602 | Two-Head Integration Note | draft |
| RES-603 | Speculative Cross-Stream | draft |
| RES-604 | QD-TER Bridge Status | stable |
| RES-605 | leCore Integration Bridge | stable |
| RES-606 | Metric Bridge Candidate Derivations | candidate |

The status page (RES-604) is the canonical open/closed inventory. Individual
docs state their own scope; the status page aggregates them.

## Dependency graph

    RES-100 ─▶ RES-101 ─▶ RES-102
        │
        ▼
    RES-200 ─▶ RES-201 ─▶ RES-202
        │
        ▼
    RES-300 ─▶ RES-301 ─▶ RES-302 ─▶ RES-303
        │
        ▼
    RES-304  RES-305  RES-306 ─▶ RES-307 ─▶ RES-308 ─▶ RES-309
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
    RES-320 ─▶ RES-321 ─▶ RES-322
        │
        ▼
    RES-400 ─▶ RES-401 ─▶ RES-402
        │
        ▼
    RES-500 ─▶ RES-501
        │
        ▼
    RES-600    RES-601
      │          │
      └────┬─────┘
           ▼
      RES-602 ─▶ RES-603
           │
           ▼
      RES-604 ─▶ RES-605 ─▶ RES-606
