# Guild board completion and merit

A solved board item in Resileos is a merit candidate for the guild-system.

## Flow

1. A board item is created with `guild_board(guild_id, title)`.
2. Work is done on the worker (files, tests, Lean, shell).
3. `complete_and_credit(guild_id, member, title, evidence=...)` returns:
   - a board triple on `guild:<id>`
   - a merit candidate with `relation: "merit"` and an attestation block

## Attestation shape

The candidate matches the guild-system attestation closely enough to learn into a guild hub:

| Field | Source |
|-------|--------|
| issuer_guild | guild_id |
| issuer_moniker | member |
| artifact_ref | title |
| verification_evidence | evidence string |
| score | integer |
| status | candidate |

Signature and public key stay with the guild process. Resileos does not sign.

## Learn into the hub

```text
subject: guild:<id>
relation: merit
obj: <member>:<artifact>
```

That triple is the credit on the board.

## Cross-reference

- Resileos: `src/resileos/ui/worker_tools.py` (`complete_and_credit`, `record_merit`)
- guild-system: `schemas/attestation.v1.json`, `matrices/GS-MTX-003`, `matrices/GS-MTX-004`
