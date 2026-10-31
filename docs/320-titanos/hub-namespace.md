---
doc: RES-328-hub-ns
title: Hub Namespace — User and World Memory
status: proposed
depends_on: [RES-328-hub-chat, RES-320]
referenced_by: [RES-328-router]
---

# Hub Namespace

## 1. Purpose

Learned user and world data are **first-class structured facts**, not silent weights. Hubs share Titanos mechanics (bands, learn, ask) under a **naming contract** so they do not clobber global seed knowledge.

## 2. Subject forms

| Form | Meaning | Example |
|------|---------|---------|
| `user:<id>` | End-user basin | `user:alice` |
| `world:<id>` | Shared scenario / campaign | `world:demo` |
| `org:<id>` | Tenant / team | `org:acme` |

- `<id>`: lowercase `[a-z0-9_]{1,64}` recommended.
- Global (non-hub) subjects stay unprefixed (`Zeus`, `Athena`, …).
- Router and learn APIs **must** use the prefix for hub writes.

## 3. Relation vocabulary (v1)

Keep small; extend deliberately.

| Relation | Use |
|----------|-----|
| `prefers` | Durable preference value |
| `stated` | User-asserted fact about self |
| `setting` | Config-like key |
| `note` | Free short memo (still a triple, not an essay) |

Objects are short strings (or normalized tokens). Multi-valued pairs are allowed; recall via `ask_list` / SPARQL, not single-value assumption.

## 4. Isolation rules

1. Hub learn never overwrites a global subject by accident — subject string must include the prefix.
2. TOOL_FACT about global entities uses global names; HUB_RECALL uses hub subjects.
3. Export / delete hub = delete or dump triples matching subject prefix.
4. Attractors: prefer deferred / bands-first on bulk hub import (same as scale profile guidance).

## 5. API mapping

```text
learn(subject="user:alice", relation="prefers", obj="exact_answers")
ask("user:alice", "prefers")  →  ["exact_answers", ...]
```

Demo: `scripts/tool_mouth_demo.py --hub-user alice` exercises this path.

## 6. QVR / training alignment

“Train the state” = supervised writes of interaction residue into hub (and optional later carrier adaptation). It does **not** mean the mouth’s prior may override hub or global Oracle rows.
