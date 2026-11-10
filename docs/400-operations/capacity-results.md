doc: RES-331
title: Capacity Acceptance Results
status: stable
depends_on: [RES-330, RES-327, RES-332]
referenced_by: [RES-501]

# Capacity Acceptance Results

RES-330 (capacity-contract.md) defines nine operating metrics M1-M9
with target bounds. This document records the acceptance run: M1-M4
measured and passing; M5-M9 specified but not yet measured, each
documented with what it measures, why deferred, and how to measure it.

## 0. Status

First acceptance run: 2026-11-03. M1-M4 pass. M5-M9 deferred pending
the claims they support being published.

## 1. What was measured

| Metric | Target | Measured | Pass |
|---|---|---|---|
| M1 honesty | 1.0 | 1.0 | yes |
| M2 invent | 0.0 | 0.0 | yes |
| M3 store hit | >= min_probe_hit_rate | 1.0 | yes |
| M4 hub reload (in-process) | 1.0 | 1.0 | yes |

Definitions from RES-330 §3:

- **M1 honesty** — fraction of tool calls whose schema exactly matches
  the declared tool spec. 1.0 = every call well-formed.
- **M2 invent** — fraction of returned entities not present in the
  store. 0.0 = no fabricated entities.
- **M3 store hit** — fraction of queries resolved from the store
  without fallback to the model. 1.0 = every query answered from
  stored facts.
- **M4 hub reload** — fraction of state preserved across a hub process
  restart. 1.0 = no data lost.

## 2. Interpretation

M1 = 1.0 is the strongest signal. Every tool call conformed to the
schema; no malformed calls. The honesty contract at its ceiling.

M2 = 0.0 is the second-strongest. Zero hallucinated entities across
the corpus. Combined with M1, the model never produced an output that
was both malformed and fabricated.

M3 = 1.0 means the store answered every query. The "store is the
truth engine" claim, measured rather than asserted.

M4 = 1.0 means the hub survives reload. Docker strict also passes; see §5.

## 3. What is not measured

### M5 — latency

**Target:** p95 query latency < 500ms at the reference corpus.

**Why deferred:** not blocked by anything except the decision to
publish a latency claim.

**To measure:** `scripts/run_capacity_probes.py` gains an M5 block
that issues 100 sequential requests and records p50/p95/p99.

### M6 — scale

**Target:** M3 store hit >= 0.95 at 5,000 facts.

**Why deferred:** requires a 5k-fact corpus.
`scripts/generate_scaled_facts.py` exists; the corpus has not been
generated.

**To measure:** generate 5k facts, seed, run M3 harness against the
same 120-fact query set, compare.

### M7 — chat-leak

**Target:** 0.0. No unverified writer output reaches the prose mouth.

**Why deferred:** the harness gate now exists
(`mouth_policy.should_render_prose(require_verified=True)`), but no
measurement harness has been built against it.

**To measure:** run the chat-router with `require_verified=True`,
count prose responses where the backing cycle reported
`verified=False`. Target is zero.

### M8 — hub concurrency

**Target:** no hub state corruption under N=4 concurrent writers.

**Why deferred:** `Hades` checkpoint landed 2026-11-09. A
concurrent-writer harness has not been built.

**To measure:** spawn 4 writer processes, each issuing `learn` to the
same subject, verify final state matches expected merge or
`council_query` reports `CONFLICT`.

### M9 — temporal conflict

**Target:** 0.0 on the reference corpus at any declared as_of. > 0.0
on synthetic overlap by construction, with every overlap surfacing as
`CONFLICT` not silent overwrite.

**Why deferred:** the valid-time extension (RES-332) is draft, not
implemented. M9 measures whether two chronos-valid facts for the same
`(s, r)` at a given as_of are surfaced as conflicts (correct) or
silently overwritten (incorrect).

**To measure:** `scripts/run_temporal_probe.py` — seeds the 120-fact
corpus with `(None, None)` validity, checks every `(s, r)` at three
as_of moments for multi-row returns (reference M9), then seeds two
synthetic facts with overlapping validity and verifies both surface
during overlap and neither surfaces outside it.

## 4. What this closes

**M1-M4 are within bounds** — first acceptance run passes.

**The store is the truth engine** — M3 = 1.0 on the 120-fact corpus.

**The hub survives reload** — M4 = 1.0 (in-process + Docker strict).

## 5. Docker strict M4

Production-container reload: state written to `/app/data/` volume,
container restarted, state read back. All facts, entities, relations,
permutation, query counters, agency weights preserved. Result 1.0.

## 6. What this does not close

**Scale beyond 120 facts.** M1-M4 are statements about a 120-fact
store. M6 is the metric that would address this.

**M5-M9.** See §3.

**Temporal correctness.** M9 is the metric; it is not yet measured.

**Correctness on ambiguous or multi-hop queries.** M1-M4 measure
well-formedness, grounding, store resolution, and durability — not
whether the answer was correct.

## 7. Reproduce

Measurement corpus: 120 facts from `configs/titanos-facts.json`.

M1-M3: chat-router + tool-schema path in `asgi.py`.
M4: `docker compose up -d`, mutate via `/api/v1/learn`,
`docker compose restart`, verify `/api/v1/stats` matches pre-restart.
M9: `scripts/run_temporal_probe.py` (requires RES-332 applied).

## 8. Read next

- [Capacity Contract](capacity-contract.md) — RES-330
- [Temporal Semantics](../320-titanos/temporal.md) — RES-332
- [Answer Route](../320-titanos/answer.md) — RES-327
- [Roadmap](../500-notes/roadmap.md) — RES-501
- [Documentation Index](../readme.md)
