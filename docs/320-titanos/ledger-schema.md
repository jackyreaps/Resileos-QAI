---
doc: RS-INF-002
title: Guild Ledger Schema
version: "1.0"
status: draft
depends_on: [RS-INF-001]
---

# Guild Ledger Schema

Authoritative Merit and Credits balances. Titanos holds membership graph and event triples.

## Path

Default: `artifacts/guild_ledger.json`  
Production: `RESILEOS_GUILD_LEDGER` (e.g. `/app/data/guild_ledger.json`).

## Schema

```json
{
  "version": 1,
  "members": {
    "<guild_id>:<moniker>": {
      "merits": 0,
      "credits": 0
    }
  }
}
```

- `merits`: integer ≥ 0; increase only via award; never purchasable  
- `credits`: integer ≥ 0; grant or burn; never convert to/from Merit  

## Events (Titanos)

`(org:guild:G:member:M, merit_event, +N:reason)`  
`(org:guild:G:member:M, credit_event, ±N:reason)`

## API discipline

Allowed: award_merits, grant_credits, burn_credits, member_status.  
Forbidden: Merit↔Credits exchange endpoints.
