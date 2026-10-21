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
```

Recommended behavior:

1. Attempt structured resolution via parent Titanos query / SPARQL.
2. If resolved → return Answer (cite store; no generation required).
3. If miss and residual/scar context is available → optional compose or
   carrier modulation (RES-315) against a frozen downstream surface;
   still return structured Answer or None.
4. If outside competence → None (abstain). Never invent triples.

## 3. Inputs Zeus may read (read-only)

- Titanos query results and SPARQL traces
- Control packet / residual monitors (scar energy, \(\Lambda\) trajectory)
- Field \(R\) (same family of gates as ingest R-gate)
- Stream HV / mask-stack HV (RES-311, RES-312)
- CSI window for agency fitness updates

Zeus writes no state into ResidualCore. Agency fitness and optional
carrier weights are the only mutable surfaces (RES-307, RES-315).

## 4. Eat criteria

Uses RES-307 thresholds unchanged:

- Rolling mean CSI below `eat_threshold_csi`
- Contribution EMA below `eat_threshold_contrib`
- At least `min_queries_before_eat` routed queries

When eaten, Zeus is removed from the routing pool. Weight is not
transferred. Parent continues with remaining children and pure Titanos
lookup.

## 5. Explicit non-goals

- Native open-ended text generation (Claim C)
- Differentiable ResidualCore / Kuramoto training
- Replacing leCore as external capability router
- Bypassing ingest: external model text still enters only via RES-323

## 6. Implementation sketch

```python
group.add_child(
    "zeus",
    handler=zeus_handler,   # closes over store, optional carrier
    weight=1.0,
)
```

Carrier training remains the RES-315 experiment: frozen substrate,
frozen parent model, train carrier only. If that experiment shows no
downstream signal, Zeus stays a structured composer on top of Titanos.

## 7. Status

Draft. No theorem claims Zeus improves answer quality. Fitness and eat
rules are operational (RES-307 heuristic).
