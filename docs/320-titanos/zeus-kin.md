---
doc: RES-334-kin
title: Zeus Kin — Operator Contracts
status: proposed
depends_on: [RES-333-olympus, RES-324, RES-307, RES-332]
---

# Zeus Kin — Operator Contracts

Handler shape matches RES-307 / Zeus where applicable:

    handler(parent, subject, relation, inverse) -> Any | None

Observers and organizers may instead expose **side interfaces** (stats hooks, policy apply, context index) invoked by the agency loop, not by every query.

## 1. Zeus (existing)

- **Verb:** residual structured answer or decline  
- **Contract:** RES-324  
- **Fitness:** accept rate, CSI (caller-recorded)

## 2. Iris (observer)

- **Verb:** observe  
- **Inputs:** recent query outcomes, ops metrics, agency child stats, Hermes probe utility  
- **Output:** structured report (M1–M5 style fields, loop flags, persona deltas, context-hit ratios)  
- **Query handler:** always `None` (does not answer user facts)  
- **Failure:** silent if metrics unavailable — never fabricates store rows

## 3. Metis (organizer)

- **Verb:** organize agency  
- **Inputs:** Iris report thresholds  
- **Actions:** adjust child weights, enable/disable, optional router policy flags, Hermes depth/budget caps  
- **Constraints:** cannot call `learn` on world triples; cannot bypass NONE_CHANNEL  
- **Query handler:** `None` unless explicitly queried for `agency` / `policy` subjects under a reserved namespace (`sys:agency`, …)

## 4. Hermes (context navigator)

- **Verb:** navigate / layer context  
- **Role:** Hierarchical, meaning-first organization of keys or residual probes so long context and multi-band queries do not require full scans. Inspired by hierarchical sparse-attention research (e.g. LSA-class group-then-drill); **not** an in-repo implementation of any external kernel.
- **Inputs:** query embedding or subject/relation signature; optional depth budget from Metis  
- **Actions:**  
  1. Form or consult coarse meaning groups over stream / hub / recent packets  
  2. Select top groups  
  3. Sparse probe into Titanos / bands only inside those groups  
  4. Return ranked candidates or `None` if empty  
- **Constraints:**  
  - Never invents triples; empty groups → decline or hand off to Zeus full path  
  - Does not persist hierarchical indexes as facts (indexes are ephemeral or capacity-capped caches)  
  - Write path remains Demeter / `learn` only  
- **Query handler:** may answer only when subject/relation is under reserved context namespaces or when agency routes “long-context” class; otherwise `None`  
- **Fitness:** hit utility (relevant rows found / FLOPs), false-empty rate, regression on M1 when Hermes is preferred over full Zeus path  
- **Status:** docs-first; implement after Iris/Metis and strict M4 green

## 5. Demeter (eat)

- **Verb:** propose digest  
- **Inputs:** external text or tool results under leCore  
- **Actions:** emit candidate triples for human or policy-gated `learn`  
- **Constraints:** candidates ≠ committed facts until learn succeeds  
- **Aligns with:** RES-325 eat strategy

## 6. Asclepius (excise)

- **Verb:** sparse prior repair (mouth / mask / carrier only)  
- **Inputs:** failure diagnosis (loops, invent under persona, tool non-adherence)  
- **Actions:** propose patch + mandatory probe; rollback on M1/M2 regression  
- **Constraints:** **zero** writes to Titanos fact ledger; capacity-capped touch fraction  
- **Status:** later than Iris/Metis/Hermes skeleton; after hub M4 strict green preferred

## 7. Mnemosyne (personified metrics)

- **Verb:** score development under persona envelopes  
- **Inputs:** same probes as Iris, run with persona system pack; optional Hermes-on vs Hermes-off A/B  
- **Outputs:** heavy-weighted scores: tool adherence, invent rate, hub-pref consistency, unneeded-tool rate, context-layer utility  
- **Use:** feeds Metis; does not redefine truth frames  
- **Frame gate:** only envelopes allowed by finished atlas/openness docs

## 8. Registration sketch

```text
agency.register("zeus", zeus_handler, weight=1.0)
agency.register("iris", iris_noop_handler, weight=0.0)     # side channel
agency.register("metis", metis_handler, weight=0.0)
agency.register("hermes", hermes_handler, weight=0.0)     # enable when spine allows
# demeter / asclepius / mnemosyne: enable when spine checklist allows
```

Fitness and removal rules stay with RES-307 / RES-324 group policy.
