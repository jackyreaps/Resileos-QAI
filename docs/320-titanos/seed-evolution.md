---
doc: RES-337-seed
title: Seeded Evolution Module
status: implemented
depends_on: [RES-336-user-persona]
---

# Seeded Evolution

## Purpose

Append-only **seed events** plus **bootstrap** so each user session starts from durable residue (metrics, assets, persona hints). Does not invent domain facts or train weights.

## Event types

`session_start` · `fact_learned` · `query_hit` · `query_miss` · `asset_registered` · `persona_set` · `mouth_used`

## Log path

`RESILEOS_SEED_LOG` or `/app/data/seed_events.jsonl` or repo `data/seed_events.jsonl`.

## Code

| Path | Role |
|------|------|
| `src/resileos/seed/types.py` | SeedEvent, BootstrapPayload |
| `src/resileos/seed/log.py` | JSONL append / iter |
| `src/resileos/seed/metrics.py` | Aggregates |
| `src/resileos/seed/evolution.py` | record_* + bootstrap |

## Next (app wire-up)

- `GET /api/v1/seed/{user_id}/bootstrap`
- Optional hooks after `/learn` and `/query` when `X-User-Id` is set
- Studio: call bootstrap on sidebar user id
