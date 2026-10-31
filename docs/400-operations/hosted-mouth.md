---
doc: RES-400-hosted-mouth
title: Hosted Mouth — Tools-Only Fact Path
status: proposed
depends_on: [RES-328-router, RES-328-hub-ns, RES-327-tools]
---

# Hosted Mouth

## 1. Role

A hosted large model supplies **open-chat language**. It does not own empirical truth. All world/user facts go through Resileos tools or structured routes.

## 2. Required wiring

| Item | Requirement |
|------|-------------|
| Tool base URL | Resileos API (`/api/v1/tools/execute`, `/api/v1/answer`, `/api/v1/learn`) |
| Auth | API key on every tool call |
| System policy | On tool empty/abstain: say unavailable; never invent |
| Chat router | [chat-router.md](../320-titanos/chat-router.md) classes before generation |

## 3. Turn loop

1. Router classifies turn.
2. If TOOL_FACT / HUB_RECALL → model emits tool calls only for claims.
3. If HUB_LEARN → learn via API, then confirm in natural language.
4. If SOFT_CHAT → generate without tools; no new empirical claims.
5. Log tool statuses for eval (hit / miss / abstain).

## 4. Eval bar (same as tool_mouth_demo)

- Known triple → exact or list match  
- Unknown → no invention  
- Abstain path → refuse  
- Hub user → recall learned preference  

## 5. Non-goals

- Finetune that silently becomes the fact store  
- Decoder as recovery gate  
- Replacing Titanos with parametric memory  
