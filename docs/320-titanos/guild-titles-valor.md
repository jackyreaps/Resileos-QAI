---
doc: RS-INF-004
title: Titles and Valor Records — Bridge to Higher-Order Representation
status: draft
depends_on: [RS-INF-001, RS-INF-003, RES-329-guild]
references: [GS-CHR-002, GS-CHR-010, GS-CHR-012]
---

# Titles and Valor Records

## Purpose

Local **ranks** are Merit bands. **Titles** are named, non-purchasable achievements bound to a moniker. **Valor records** are a restricted title family for cost-bearing and coherence under load.

Together they form a **portfolio** that Local Charters and GS-CHR-012 may use as *eligibility and evidence* for higher-order representation (Convocation seats, Imperium class recognition, Valor Audit inputs).

Resileos **records** the portfolio. Network bodies under GS-CHR-012 **grant representation**. Titles never auto-appoint Steward, Princeps, or Sovereign.

## Definitions

| Term | Meaning |
|------|---------|
| Rank | Derived from Merit thresholds (`RankTable`) |
| Title | Durable slug awarded after verification (multi per moniker) |
| Valor record | Title-family event: cost borne, coherence under load, belief-line, judgment accepted |
| Portfolio | Rank + titles + valor events for one moniker in one guild |
| Representation | Network role under GS-CHR-012 — not a Resileos API power |

## Rules

1. Titles are earned, not bought. Credits never purchase titles or valor.
2. Award requires a reason and optional evidence ref (`world:` or external hash).
3. Valor claims may be stored as pending; **accomplished** only after attestation flag or published audit ref.
4. Rank labels stay local. Prefer `rank` over “class” in runtime (Imperium “earned class” is network-level).
5. Local Steward rank ≠ Convocation ceremonial Steward.

## Subjects

```text
org:guild:<id>:member:<moniker>
  title          multi slug
  valor_event    multi kind:status:ref

org:guild:<id>:title:<slug>
  name, description, status
```

## CHR-012 bridge (policy only)

| Model | Portfolio used as |
|-------|-------------------|
| Convocation | Eligibility signal for assembly / candidacy (still elected) |
| Imperium | Evidence toward earned-class recognition (Senate recognizes) |
| Sovereignty | Inputs to Valor Audit — not automatic accession |

## Code

`src/resileos/answer/guild_titles.py` · tests in `tests/test_guild_titles.py`
