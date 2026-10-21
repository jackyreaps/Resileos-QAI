---
doc: RES-324
title: Zeus Child (Residual Specialist)
status: draft
depends_on: [RES-307, RES-315, RES-320, RES-321, RES-322, RES-323]
referenced_by: []
---

# Zeus Child (Residual Specialist)

Zeus is an **AgencyChild** (RES-307), not a second store and not a
transformer replacement. It is a specialized handler that may use
residual/scar state, field order parameter \(R\), CSI, and the running
stream when Titanos lookup is insufficient.

## 1. Doctrine

| Layer | Role |
|-------|------|
| Titanos (RES-320–322) | Durable exact memory |
| Ingest (RES-323) | Eat external sources into φ-ladder + store |
| leCore (RES-605 / RES-608) | Gate external models and tools |
| **Zeus (this doc)** | Internal child: residual/scar-conditioned action |

Zeus does **not** route HTTP capabilities. That is leCore.
Zeus does **not** persist facts. That is Titanos.
Zeus **may** return `None` (decline); the parent falls through.

## 2. Handler contract

Matches RES-307:

```text
handler(parent, subject, relation, inverse) -> Answer | None
