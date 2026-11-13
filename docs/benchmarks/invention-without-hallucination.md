---
doc: BENCH-003
title: Invention Without Hallucination
status: measured — near-miss CANDIDATE exists; novel relations still abstain
depends_on: [BENCH-002, kin-eat]
referenced_by: [MKT-001]
---

# Invention Without Hallucination

**Current status.** `Titanos.ask` / `chain` can return `CANDIDATE`
when an exact close fails and a stored neighbour or a partial hop
exists. `value` stays null, `unverified` is true, and nothing is
learned. Unknown entities, relations with no facts, and empty slots
still return `ABSTAINED`. This is not open-ended generation.

What is live today:

| Behavior | Status |
|---|---|
| Stored facts returned exactly | Live |
| Chain / derivation with provenance | Live |
| Unknown relations abstain | Live |
| Near miss of a stored slot, value left null | Live as `CANDIDATE` |
| Novel relation with no stored neighbour | Abstains. Not marked as a new fact |

**The claim that is currently true.** On unknown relations the system
abstains rather than inventing. An LLM baseline given the same facts
still invents on some fraction of unknowns. That is the invent-rate row
in `memory-vs-llm.md`.

**What is true about candidates.** A near miss can be marked
`CANDIDATE` and is not asserted: the value field stays empty, and
`learn` is not called. A novel relation with no stored neighbour still
abstains. This is not a claim of open-ended composition.

## What the benchmark measures today

Run `scripts/ops/bench_invention.py` against a live API. A `CANDIDATE`
keeps a null value, so interpret the output as:

- derivation_rate — chain works or it does not
- novelty_rate — expected near 0 (nothing invented)
- assertion_rate_on_novel — expected 0 (abstention, not marking)

That table is honest. It is the abstention claim, not the invention
claim.

## Results

Run on 2026-11-10 against `http://127.0.0.1:8000/api/v1` with `RESILEOS_AUTH_BYPASS=1`. No LLM key was set.

| Metric | Value |
|--------|-------|
| derivation_rate | 0.0 |
| derivation_grounding_rate | 0.0 |
| invention_assertion_rate | 0.0 |
| p50_ms | 3.4 |

The two derivation probes are SPARQL compositions. Both returned no rows (`got: []`), so the derivation rate is 0. The two invention probes (`carol likely_commutes_to`, `alice sibling_of`) returned `ABSTAINED` and null, so nothing invented was asserted. Latencies were 2.7, 2.0, 3.4, and 44.7 ms. The script's `p50_ms` is 3.4. No LLM key was set.

## What the candidate status is

`CANDIDATE` is a near miss: a stored neighbour or a partial hop, with
`value` null and `unverified` true. It does not become a fact unless a
later verified learn goes through Zeus. A relation with no stored
neighbour still abstains. This is not open-ended composition.
