---
doc: RES-330-guild-infra
title: Resileos as Guild System Infrastructure
status: program
---

# Resileos as Guild System Infrastructure — Implementation Program

## 1. Three projects

| Project | Owns | Does not own |
|---------|------|----------------|
| Guild System GS-* | Compact, charters, merit policy | Runtime store, API |
| QD-TER / Human Medium | Framework claims, GS-001 pointer | Hosted console, Titanos |
| Resileos-QAI | Titanos hubs, mouth, world assets, guild state API | Compact authority |

Policy in GS-*/Human Medium. Operational state in Resileos hubs.

## 2. Hub map

- org:guild:id — guild
- org:guild:id:member:moniker — role, circle, events
- org:guild:id:work:id — Guild Work
- world:campaign — shared campaign
- world:id:asset:aid — media/codex paths
- user:moniker — optional prefs
- ledger: artifacts/guild_ledger.json Merit+Credits

## 3. Basics

Now: host, hub learn, world register, join/work/complete, merit/credits, mouth, api_routes.
Next: mount app.py, env ledger path, save on mutate, API moniker/credits, guild CLI.
Out: attestation, Chamber, Defense Fund, legal fork, tax annex, ZKP.

## 4. Work kinds

claim_review | derivation | code | audit | docs | world | teaching

## 5. Day flow

join -> post work -> register artifact -> complete (+merit/credits) -> burn credits -> status

## 6. Phases

A Infra live. B Local pilot guild. C Interop export when GS-CHR-009. D Doc links only no merge.

## 7. Success

Join works; Merit award-only; Credits burnable; work done; assets recall; survive restart.

## 8

Resileos runs hub+ledger; Guild defines Compact validity; Human Medium owns framework truth; meet at namespaces not merged repos.
