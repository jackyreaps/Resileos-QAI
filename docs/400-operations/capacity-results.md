doc: RES-331
title: Capacity Acceptance Results
status: stable
depends_on: [RES-330, RES-327]
referenced_by: []

# Capacity Acceptance Results

RES-330 (capacity-contract.md) defines eight operating metrics M1-M8
with target bounds. This document records the first acceptance run:
M1-M4 measured, all four within bounds. M5-M8 remain unmeasured.

## 0. Status

First acceptance run: 2026-11-03. Four of eight metrics measured. All
four pass. The other four (M5 latency, M6 scale, M7 chat-leak,
M8 hub concurrency) are deferred until the claims they support are
published.

## 1. What was measured

| Metric | Target | Measured | Pass |
|---|---|---|---|
| M1 honesty | 1.0 | 1.0 | yes |
| M2 invent | 0.0 | 0.0 | yes |
| M3 store hit | >= min_probe_hit_rate | 1.0 | yes |
| M4 hub reload (in-process) | 1.0 | 1.0 | yes |

Definitions from RES-330 §3:

- **M1 honesty** — fraction of tool calls whose schema exactly matches
  the declared tool spec. 1.0 = every call was well-formed.
- **M2 invent** — fraction of returned entities not present in the
  store. 0.0 = no fabricated entities.
- **M3 store hit** — fraction of queries resolved from the store
  without fallback to the model. 1.0 = every query answered from
  stored facts.
- **M4 hub reload** — fraction of state preserved across a hub
  process restart. 1.0 = no data lost.

## 2. Interpretation

M1 = 1.0 is the strongest signal in the set. Every tool call in the
measurement corpus conformed to the schema; no malformed calls, no
missing arguments, no extra fields. The honesty contract at its
ceiling.

M2 = 0.0 is the second-strongest. Zero hallucinated entities across
the corpus. Combined with M1, the model never produced an output that
was both malformed and fabricated — the two failure modes the
capacity contract exists to prevent.

M3 = 1.0 means the store answered every query the harness posed. The
"store is the truth engine" claim, measured rather than asserted.

M4 = 1.0 means the hub survives reload. In-process path returns 1.0.
The strict M4 (production Docker container, restart-and-reload) was
measured separately and also passes; see §5.

## 3. What is not measured

| Metric | Why deferred |
|---|---|
| M5 latency | Not published as a claim |
| M6 scale | Requires 5k+ fact corpus |
| M7 chat-leak | Requires chat-router + persona measurement harness |
| M8 hub concurrency | Requires multi-process harness |

M5-M8 are not blocked by hardware. They are blocked by whether the
corresponding claims are being published. Until a public claim depends
on M5-M8, they stay unmeasured.

## 4. What this closes

**"M1-M4 are within bounds"** — yes, first acceptance run passes on
all four.

**"Does the model invent entities"** — M2 = 0.0 over the measurement
corpus.

**"Does the store answer queries"** — M3 = 1.0.

**"Does the hub survive reload"** — M4 = 1.0 (in-process + Docker
strict, see §5).

## 5. Docker strict M4

The production-container reload measurement:

- Hub state written to `/app/data/` volume
- Container restarted (not just process)
- State read back on startup
- All facts, entities, relations, permutation, query counters,
  agency weights preserved

Result: 1.0. No state lost across container restart. This is the
strict M4 — the in-process §1 measurement is the weaker variant.

## 6. What this does not close

**Scale beyond 120 facts.** All four M1-M4 measurements use the
120-fact corpus from `configs/titanos-facts.json`. M3 is a statement
about a 120-fact store, not about 5k or 50k. M6 (scale) is the metric
that would answer this and it is unmeasured.

**M5-M8.** See §3.

**Accuracy on ambiguous or multi-hop queries.** M1-M4 do not measure
whether the answer was correct — they measure whether the output was
well-formed (M1), grounded (M2), store-resolved (M3), and durable
(M4). Correctness of store-resolved answers is bounded by store
contents, not by the model.

## 7. Reproduce

Measurement corpus: 120 facts from `configs/titanos-facts.json`.

M1-M3 harness: the chat-router + tool-schema path in `asgi.py`.
Docker strict M4: `docker compose up -d`, mutate state via
`/api/v1/learn`, `docker compose restart`, verify `/api/v1/stats`
matches pre-restart.

Exact probe invocations recorded in
`scripts/run_capacity_probes.py` (see that file for the per-metric
commands).

## 8. Read next

- [Capacity Contract](capacity-contract.md) — RES-330
- [Answer Route](../320-titanos/answer.md) — RES-327
- [Roadmap](../500-notes/roadmap.md) — RES-501
- [Documentation Index](../readme.md)
