---
doc: RES-336-user-persona
title: User Profile and Persona in Studio
status: implemented
depends_on: [RES-335-persona, RES-328-hub-ns]
---

# User Profile and Persona in Studio

## Purpose

Make the hosted product **sticky and useful** without turning the mouth into an inventor:

- Durable prefs under `user:<id>:*`
- Persona envelope packs (tone only)
- Interest tags from usage signals
- Turn count for light continuity

## Rules

1. Persona changes **tone and guidance**, never invents store facts.
2. Biographical claims only if the user taught them (`remember` / learn).
3. Aligns with RES-335: envelope is style + scope, not unbounded character drift.

## Code

| Path | Role |
|------|------|
| `src/resileos/answer/user_profile.py` | Load/save/shape |
| `ui_studio.py` | Sidebar user id, persona, auto-save on chat turns |

## Packs

`honest` · `guide` · `builder` · `mythic` — see `PERSONA_PACKS` in code.
