---
doc: RS-INF-003
title: Guild Classes and Work Board
status: implemented
depends_on: [RS-INF-001, RES-329-guild]
references: [GS-CHR-002, GS-CHR-010]
---

# Guild Classes and Work Board

## Hierarchy without a global authority

Large groups scale by **many autonomous guilds** (Compact polycentricity), not one rank pyramid for the whole system.

Inside one guild:

| Layer | Mechanism |
|-------|-----------|
| **Rank (class)** | Merit thresholds in a local `RankTable` (charter-published) |
| **Circle** | formalist / empirical / forge / distribution (orthogonal) |
| **Board** | open → claimed → done work / bounties |

Default ranks: `initiate` (0) → `member` (10) → `journeyman` (50) → `senior` (150) → `steward` (400). Override in Local Charter.

Ranks grant **local capability labels** only. They do not create Compact authority, Chamber power, or cross-guild command.

## Board / bounty flow

```
post_bounty → claim_bounty → complete_bounty (+Merit / +Credits from bounty_*)
```

Same `org:guild:<id>:work:<id>` subjects as the guild console; board is a view + helpers.

## Code

`src/resileos/answer/guild_classes.py` · `tests/test_guild_classes.py`

## Scaling note

| Population | Pattern |
|------------|---------|
| Tens | One guild, default ranks, one board |
| Hundreds | Circles shard the board; stewards moderate locally |
| Thousands+ | Multiple chartered guilds; interop via GS-CHR-009; no global rank |
