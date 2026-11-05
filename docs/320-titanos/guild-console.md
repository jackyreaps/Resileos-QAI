---
doc: RES-329-guild
title: Guild Operational Store
status: implemented
depends_on: [RES-328-hub-ns, RES-328-workbench]
references: [GS-FND-002, RS-INF-001]
---

# Guild Operational Store

Hostable Titanos state for a chartered guild: membership, Merit, Credits, work items.

Policy lives in [guild-system](https://github.com/jackyreaps/guild-system). This module is runtime only.

## Subjects

`org:guild:<id>` · `org:guild:<id>:member:<moniker>` · `org:guild:<id>:work:<id>`

## CLI

```bash
python scripts/guild_console.py create --guild builders --name "Builders"
python scripts/guild_console.py join --guild builders --moniker alice --circle forge
python scripts/guild_console.py work --guild builders --work-id t1 --title "Index formal refs" --kind derivation --moniker alice
python scripts/guild_console.py complete --guild builders --work-id t1 --moniker alice --merit-award 5 --credit-award 2
python scripts/guild_console.py status --guild builders --moniker alice
```

## Code

| Path | Role |
|------|------|
| `src/resileos/answer/guild.py` | Join, ledger, work |
| `src/resileos/answer/api_routes.py` | HTTP |
| `scripts/guild_console.py` | CLI |
| `docs/320-titanos/ledger-schema.md` | RS-INF-002 |
