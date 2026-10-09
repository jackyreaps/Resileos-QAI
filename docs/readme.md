---
doc: RES-000
title: Documentation Index
status: stable
depends_on: []
referenced_by: [RES-100]
---

# Resileos-QAI Documentation

**Version:** see [`/version`](../version) · **Changelog:** [`/changelog.md`](../changelog.md)

**Status vocabulary.** Documents carry one of: `draft`, `stable`, `deprecated`,
`conditional`, `conjectural`. `conditional` means "true under stated
assumptions"; `conjectural` means "formal structure awaiting physical input".
Documents outside the first three values live in the 600-series.

## Reading order

Foundations:

1. [Overview](100-foundations/overview.md) — RES-100
2. [Architecture](100-foundations/architecture.md) — RES-101
3. [Design Principles](100-foundations/design-principles.md) — RES-102

QD-TER bridge:

4. [FEP Reduction Bridge](600-qdter/fep-reduction.md) — RES-600
5. [Non-Dual Adaptation Layer](600-qdter/non-dual-adaptation.md) — RES-601
6. [Two-Head Integration Note](600-qdter/integration.md) — RES-602
7. [Speculative Cross-Stream Layer](600-qdter/speculative-cross-stream.md) — RES-603

## Categories

| Range | Category | Entry point |
|---|---|---|
| 100 | Foundations | [Overview](100-foundations/overview.md) |
| 200 | Classical Core | [Classical Core](200-core/classical-core.md) |
| 300 | Generative Substrate | [HDRIFT Adapter](300-substrate/hdrift-adapter.md) |
| 400 | Operations | [Run Config](400-operations/run-config.md) |
| 500 | Notes & Roadmap | [Behavioral](500-notes/behavioral.md) |
| 600 | QD-TER Bridge | [FEP Reduction](600-qdter/fep-reduction.md) — RES-600 … RES-603 |
| 900 | Reference | [Glossary](900-reference/glossary.md) |

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
    RES-400 ─▶ RES-401 ─▶ RES-402
                   │
                   ▼
    RES-500 ─▶ RES-501
                   │
                   ▼
    RES-600  (related)  RES-601
                   │
                   ▼
                 RES-602 ─▶ RES-603
