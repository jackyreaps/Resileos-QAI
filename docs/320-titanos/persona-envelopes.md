---
doc: RES-335-persona
title: Persona Envelopes — Archetypal Development without Ledger Capture
status: proposed
depends_on: [RES-333-olympus, RES-334-kin, RES-331, RES-330]
related_to: [frame-atlas-bridge, hub-namespace, ops-metrics]
---

# Persona Envelopes

## 1. Definition

A **persona envelope** is a finite bundle:

- system prompt / style pack  
- allowed tool set  
- hub subject scope (`user:`, `world:`, …)  
- **metric weight vector** for Mnemosyne (honesty heavy by default)  
- optional Hermes depth budget (context layering allowed or forced-off)  
- optional frame tags (when atlas entries are finished)

It is **not** a license to assert unstored facts.

## 2. Growth / evolution

| Stage | Meaning |
|-------|---------|
| Envelope v0 | Tool-first, no persona weight tuning, Hermes off |
| Envelope v1 | Mnemosyne scores under one pack; Metis may rebalance agency |
| Envelope v2 | Hermes optional on long-context class; metrics include context-hit utility |
| Envelope v3 | Multiple packs; frame-constrained axes only |
| Envelope v4+ | Optional Asclepius on mouth prior if probes demand |

Evolution is **envelope versioning + probe history**, not unbounded character drift.

## 3. Heavy-weighted personified metrics (default)

| Metric | Default weight | Sense |
|--------|----------------|-------|
| Tool adherence (M1-class) | high | Must not drop under persona |
| Invent rate (M2-class) | high (penalty) | Must stay ~0 |
| Hub preference consistency | medium–high | Persona may use hub, not invent it |
| Unneeded tool calls | medium | Exact, not noisy |
| Soft-chat leak (M5) | high (penalty) | |
| Context-layer utility (Hermes) | medium when enabled | Hit utility vs full-scan baseline; false-empty penalized |

Fluency / charm metrics, if any, stay **strictly below** honesty weights.

## 4. Archetypal branches (from frames when finished)

When frame documents are finished, they may **label** envelopes (e.g. stewardship-leaning vs diagnostic-leaning). They do **not** inject school doctrines into Titanos relations. Branching is:

```text
finished frame openness + axes
    → allowed envelope tags
        → Mnemosyne weight templates
            → optional Hermes depth
                → Metis may enable/disable packs
```

Unfinished frames → no runtime branch.

## 5. Hierarchical context note (LSA-class inspiration)

External hierarchical sparse-attention work (meaning-first groups, then drill-in) informs **Hermes** only as a **navigation contract**. Product durable memory remains Titanos + hub. Any useful residue discovered through Hermes probes must still be **Demeter-eaten** via `learn` if it is to persist; attention-state or index caches are not the ledger.

## 6. qwenFS / in-weight FS note

Compiled-in-weight filesystems remain **persona/session organization experiments**. Durable product memory remains Titanos + hub. Any useful residue must be Demeter-eaten into learn.
