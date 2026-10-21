---
doc: RES-325
title: Eat Strategy (Titanos vs Transformers)
status: draft
depends_on: [RES-323, RES-324, RES-605, RES-608]
referenced_by: []
---

# Eat Strategy (Titanos vs Transformers)

## 1. Three claims

| Claim | Meaning | Status |
|-------|---------|--------|
| **A** | Titanos as persistence any model can query | Achievable now (API + SPARQL) |
| **B** | Titanos replaces transformers on structured fact Q&A | Achievable for triple-shaped answers |
| **C** | Titanos/Zeus replace transformers for open generation | **Not** supported by this repo |

Product direction is **A + B** plus **eat**: transformers (and other
models) are teachers/mouths; the substrate is memory.

## 2. What Titanos has that transformers lack

- Add a fact without retraining
- Exact retrieval and SPARQL trace
- Persist across sessions
- Deterministic answers for stored facts
- Multi-source consensus via ingest (RES-323)

## 3. What transformers have that Titanos lacks

- Novel text generation
- Arbitrary NL query types without decomposition
- In-context learning at scale

Those gaps are filled only by: external model via leCore (then ingest),
template prose over SPARQL, or RES-315 carrier + frozen parent — not by
claiming a native LLM.

## 4. System diagram

```text
external models/tools
        │
        ▼
   leCore (RES-605/608)     stomach / gate
        │
        ▼
   ingest (RES-323)         digests into φ-ladder
        │
        ├── Titanos store   memory
        └── Stream/masks    context
        │
        ▼
   query: Titanos → Zeus child (RES-324) → abstain
```

## 5. Build order

1. Host Titanos (HOSTING.md): seed, dual health, API tests green
2. leCore invoke → ingest policy (RES-608)
3. Template renderer for fact answers (optional prose)
4. Register Zeus AgencyChild (RES-324)
5. RES-315 carrier experiment only if generation side-channel is needed

## 6. Pitch (honest)

Every transformer forgets. Titanos does not. Ingest model outputs once,
compress into a persistent substrate, serve with exact retrieval and no
retraining. Zeus is an internal residual specialist under agency eat
rules — not a general LLM.
