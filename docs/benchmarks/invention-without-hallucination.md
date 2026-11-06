---
doc: BENCH-003
title: Invention Without Hallucination
status: draft
depends_on: [BENCH-002, kin-eat]
referenced_by: [MKT-001]
---

# Invention Without Hallucination

**The claim.** The system produces novel candidates — combinations of stored
facts that were never stored themselves — and marks them as candidates rather
than asserting them as facts. An LLM presented with the same facts produces
novel output too; the difference is that its novel output is indistinguishable
from its factual output.

This is the three-tier epistemic model:

| Tier | What it is | Asserted? |
|---|---|---|
| Fact | Stored, verifier-gated | Yes |
| Derivation | Composed from facts, traceable to source hops | Yes, with provenance |
| Candidate | Novel composition, not yet verified | **No — marked as candidate** |

A hallucination is a candidate asserted as a fact. The verifier gate and the
eat filter exist to keep the candidate tier separate from the fact tier.

## Why this is a real capability and not a slogan

The mechanism is documented in the hyperdimensional literature:

- **Controlled concept synthesis via vector algebra** — given concept vectors
  `v_a` and `v_b`, a new candidate concept vector is computed by composition.
  This is described as "controlled creativity" enabled through vector
  composition, producing "reliable reasoning without text generation."
- **Unbinding reveals analogical relations** — the unbind operation exposes
  structural relations that were not stored as explicit entries, which is the
  basis of analogical invention in VSA systems.
- **Reason-then-generate** — reasoning over hypervectors is deterministic;
  the language model is demoted to a translation organ whose output is
  fluency-only. This separation is what removes hallucination from the
  reasoning path.

Resileos implements the first two in `src/resileos/kin/` and the third in the
optional mouth backend. The benchmark below measures the result.

## What this measures

Four metrics. The last is the one that matters.

| Metric | Definition | Direction |
|---|---|---|
| **Derivation rate** | Correct 2-hop compositions with provenance attached | higher |
| **Novelty rate** | Fraction of candidates that are not already stored | higher |
| **Grounding rate** | Fraction of candidates where every constituent fact resolves to the store | higher |
| **Assertion rate** | Fraction of novel outputs presented as asserted fact rather than marked candidate | **lower** |

The product thesis is: **grounded novel candidates at zero assertion**. High
novelty with high grounding and zero assertion is invention. High novelty with
low grounding is confabulation. High novelty with high assertion is
hallucination.

## Reproduce

```bash
export RESILEOS_API_KEY=...
export RESILEOS_BASE_URL=http://127.0.0.1:8000/api/v1
# Optional LLM baseline:
export LLM_API_KEY=...
export LLM_MODEL=gpt-4o-mini
python scripts/ops/bench_invention.py
```

Writes `artifacts/report_invention.json`.

## Results

| Metric | Resileos | LLM baseline | Notes |
|---|---|---|---|
| Derivation rate | _run_ | _run_ | 2-hop, provenance required |
| Novelty rate | _run_ | _run_ | candidates not already stored |
| Grounding rate | _run_ | _run_ | every constituent fact resolves |
| **Assertion rate on novel output** | **_run_** | **_run_** | **lower is better** |
| p50 latency | _ms_ | _ms_ | |

*(Populate from `artifacts/report_invention.json` after a host run.)*

## Reading the table

The bottom-left cell — Resileos assertion rate — should be near zero, because
the API returns `status` and `frame` on every response and the candidate tier
is a distinct status. The bottom-right cell — LLM assertion rate — should be
near one, because an LLM has no mechanism to mark its output as provisional
when the prompt asks for an answer.

If those two numbers diverge, the claim "invent without hallucination" is a
measured statement. If they do not diverge, the claim is not yet supported and
the README should not make it.

## Limitations

- The candidate set is small and hand-selected. This demonstrates the metric
  shape, not a domain-scale evaluation.
- Novelty is defined against the local store, not against world knowledge. A
  candidate that is novel to the store may be well known to a human.
- Grounding measures traceability to stored facts, not truth. A grounded
  candidate can still be wrong; it is *provisional*, not *correct*.
- The honest caveat from the creativity literature: suppressing hallucination
  can suppress divergent creativity. Chain-of-verification raises divergent
  creativity while decoding-time suppression lowers it, and RAG has minimal
  effect. The candidate tier must stay permissive even as the fact tier stays
  strict. This benchmark measures whether that separation holds.

## What this does not say

- It does not say the system is creative in the human sense.
- It does not say the candidates are useful. Usefulness requires a downstream
  evaluator, which is out of scope here.
- It does not say an LLM cannot invent. It says an LLM cannot mark the
  difference between invention and assertion within a single output stream.
