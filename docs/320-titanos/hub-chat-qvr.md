---
doc: RES-328-hub-chat
title: Open chat, learned user data, and QVR-style hubs
status: draft
depends_on: [RES-327, RES-327-gate]
referenced_by: []
---

# Open chat, learned user data, and QVR-style hubs

## 1. Why open chat still matters

Funding and mainstream causal products expect **conversational interfaces** and
**learned user data**. That demand is real. It does not require giving the
decoder authority over truth.

This repo’s split:

| Layer | Role |
|---|---|
| Oracle (Titanos + gate + frame) | Unfalsifiable structured memory |
| Hub (per-user / per-world partition) | Learned interaction state as *facts* |
| Mouth (LLM or template) | Language only; tools for all claims |
| QVR-style training (Genesis lineage) | Updates hub/Oracle weights of *state*, not free hallucination |

## 2. Superintelligent *open chat* without open invention

**Allowed:** unconstrained syntax, tone, pedagogy, planning language.  
**Forbidden:** factual claims about world or user that did not come from
`resileos_ask` / `chain` / hub learn records / explicit abstain.

Protocol for a chat turn:

1. Parse user message.
2. If it requests a fact → **tool call** (or multi-tool plan).
3. If tools return `NONE_CHANNEL` / `ABSTAINED` / empty rows → mouth states
   unavailability (no fill-in).
4. If user teaches a durable preference or world fact → `learn` into **hub**
   partition (subject = user or world id), not into silent weights only.
5. Soft chat (empathy, narration) may run **without** tools only when the
   turn makes **no** empirical claim.

That is open chat as a product surface; the Oracle remains the causal spine.

## 3. Hubs and stability

A **hub** is a named memory basin (user, campaign, world, org):

- Same band-store mechanics as global Titanos (or namespaced subjects).
- Stability = recovery gate + truth-frame + deferred attractor + explicit
  learn — the same controls as the global store.
- “Training in QVR” maps here to **supervised writes of interaction residue**
  into the hub (and optional carrier adaptation later), not to replacing the
  gate with a large LM prior.

## 4. Funding-facing one-liner

> Users get a natural language product; the system still only *believes*
> what it has stored or abstains. Learned user data is first-class structured
> memory (hubs), not an opaque finetune that can override the Oracle.

## 5. Implementation hooks (this repo)

- `POST /api/v1/tools/execute` — mouth boundary
- `POST /api/v1/learn` — hub/world writes
- `derive_frame` / histogram — claim-type telemetry
- `scripts/tool_mouth_demo.py` — reference agent loop
- Scale: `scripts/run_scale_profile.py` before multi-hub production loads

## 6. What is not claimed

- That a 0.5B decoder is a safe open-chat brain.
- That hub learn replaces QD-TER formal layers.
- That Human-Medium frames other than finished Gnosis (etcetera) are runtime law.
