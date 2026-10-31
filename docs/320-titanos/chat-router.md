---
doc: RES-328-router
title: Chat Router — Tool-Required vs Soft Chat
status: proposed
depends_on: [RES-328-hub-chat, RES-327-gate, RES-327-tools]
referenced_by: []
---

# Chat Router

## 1. Purpose

Classify each user turn so open chat stays a **surface**, not a truth engine.

| Class | Meaning | Action |
|-------|---------|--------|
| `TOOL_FACT` | Empirical claim about world, store, or named entity | Must use tools / structured answer |
| `HUB_LEARN` | User teaches a durable preference or fact about self/world | `learn` into hub namespace |
| `HUB_RECALL` | Question about this user/world hub | tools with hub subject |
| `SOFT_CHAT` | Tone, pedagogy, planning language, no empirical claim | Mouth only |
| `ABSTAIN_SURFACE` | Prior tool miss / explicit refuse | Mouth states unavailability |

## 2. Decision order

Evaluate top-down; first match wins.

1. **Explicit teach** — “remember that…”, “I prefer…”, “my X is…”  
   → `HUB_LEARN`
2. **Hub-scoped question** — “what do I prefer…”, “in my workspace…”  
   → `HUB_RECALL`
3. **World / store fact** — domain, relation, who/what/when about shared entities  
   → `TOOL_FACT`
4. **Follow-up after empty/abstain tool result**  
   → `ABSTAIN_SURFACE` unless user supplies new teachable content
5. Else → `SOFT_CHAT`

When unsure whether a turn is empirical, **prefer `TOOL_FACT`**. False soft-chat is the failure mode that invents.

## 3. Execution contracts

### TOOL_FACT

1. Call `resileos_ask` and/or `resileos_chain` (or `POST /api/v1/answer`).
2. If `status` in `{NONE_CHANNEL, ABSTAINED}` or `rows` empty → mouth may only report unavailability.
3. If rows present → mouth may paraphrase **only** those rows (and declared path).

### HUB_LEARN

1. Map to `(subject, relation, obj)` under [hub-namespace](hub-namespace.md).
2. `POST /api/v1/learn` (or internal `learn`).
3. Confirm write; do not also invent a parallel “personality weight.”

### HUB_RECALL

Same as TOOL_FACT with hub subjects (`user:…`, `world:…`).

### SOFT_CHAT

No tool required. Mouth must not assert store-backed facts. If it starts to, reclassify to TOOL_FACT.

### ABSTAIN_SURFACE

Fixed pattern: state that the Oracle has no channel / no rows; offer teach path if appropriate.

## 4. Minimal router sketch (reference)

Not production NLP — a deterministic scaffold for demos and tests:

```text
if teach_cue(text): return HUB_LEARN
if hub_cue(text): return HUB_RECALL
if fact_cue(text) or entity_in_store(text): return TOOL_FACT
if last_tool_empty: return ABSTAIN_SURFACE
return SOFT_CHAT
```

Replace cues with a classifier only if it is **trained on hub+tool labels** and still cannot bypass tools on TOOL_FACT turns.

## 5. Failure modes

| Failure | Effect | Guard |
|---------|--------|-------|
| Soft-chat on facts | Invention | Prefer TOOL_FACT when unsure |
| Learn into global seed | Corruption | Hub subject prefix required |
| Mouth ignores empty tools | Hallucination | Hard stop on empty/abstain |
| Every turn soft-chat | Product lies | Metrics: tool call rate on fact probes |

## 6. Relation to funding UX

Open chat UX is allowed. Causal credibility requires TOOL_FACT and HUB_* paths for empirical content. Hosted large models are mouths with **tool-only** fact authority — see `docs/400-operations/hosted-mouth.md`.
