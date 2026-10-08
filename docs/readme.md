---
doc: RES-000
title: Documentation Index
status: stable
depends_on: []
referenced_by: [RES-100]
---

# Resileos-QAI Documentation

**Version:** see [`/version`](../version) · **Changelog:** [`/changelog.md`](../changelog.md)

## Reading order

1. [Overview](100-foundations/overview.md) — RES-100
2. [Architecture](100-foundations/architecture.md) — RES-101
3. [Design Principles](100-foundations/design-principles.md) — RES-102

## Categories

| Range | Category | Entry point |
|---|---|---|
| 100 | Foundations | [Overview](100-foundations/overview.md) |
| 200 | Classical Core | [Classical Core](200-core/classical-core.md) |
| 300 | Generative Substrate | [HDRIFT Adapter](300-substrate/hdrift-adapter.md) |
| 400 | Operations | [Run Config](400-operations/run-config.md) |
| 500 | Notes & Roadmap | [Behavioral](500-notes/behavioral.md) |
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
