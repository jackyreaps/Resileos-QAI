---
doc: RS-INF-003
title: Guild Ranks and Work Board
status: implemented
depends_on: [RS-INF-001, RES-329-guild]
references: [GS-CHR-002, GS-CHR-010, GS-CHR-012, RS-INF-004]
---

# Guild Ranks and Work Board

## Hierarchy without global authority

Large groups scale by **many autonomous guilds** (Compact polycentricity), not one rank pyramid for the whole system.

Inside one guild:

| Layer | Mechanism |
|-------|-----------|
| **Rank** | Merit thresholds in a local `RankTable` (charter-published) |
| **Titles / valor** | Named achievements + valor records ([RS-INF-004](guild-titles-valor.md)) |
| **Circle** | formalist / empirical / forge / distribution (orthogonal) |
| **Board** | open → claimed → done work / bounties |

Default ranks: `initiate` (0) → `member` (10) → `journeyman` (50) → `senior` (150) → `steward` (400). Override in Local Charter.

**Naming:** use **rank** in runtime, not “class.” Imperium’s earned class and Convocation Steward are network roles under GS-CHR-012; local `steward` rank is only a Merit band label.

Ranks and titles grant **local labels and eligibility evidence** only. They do not create Council, Senate, or Sovereign authority.

Network-scale structures (Convocation, Imperium, Sovereignty) are defined in **GS-CHR-012**. A guild may record `scale_model` for display; transition and revocation remain Guild System acts.

## Board / bounty flow

```
post_bounty → claim_bounty → complete_bounty (+Merit / +Credits from bounty_*)
```

Same `org:guild:<id>:work:<id>` subjects as the guild console.

## Code

`src/resileos/answer/guild_classes.py` · `src/resileos/answer/guild_titles.py` · tests

## Scaling note

| Population | Pattern |
|------------|---------|
| Tens | One guild, default ranks, one board |
| Hundreds | Circles shard the board; titles mark specialists |
| Thousands+ | Multiple chartered guilds; interop GS-CHR-009; portfolio evidence for CHR-012 representation |
