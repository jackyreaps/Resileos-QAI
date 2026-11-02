---
doc: RES-330
title: Capacity Contract
status: proposed
depends_on: [RES-317, RES-320, RES-327-gate, RES-401]
related_to:
  - scale-decision-2k5k
  - Human-Medium frame dimensionality scale
  - frame-atlas-bridge
---

# Capacity Contract

## 1. Intent

Before upscaling N, dim, or GPU, the system runs under **named bounds**:

- The **residual ledger** (bands / facts / SDM writes) stays complete.
- The **denoise prior** (Hopfield) and the **speech channel** (gate / mouth) stay capacity-bounded.
- Contraction is **declared** (φ-compress, bulk flush, HF cap), not silent loss of axes.

This is the same construction as a minimum-GPU / short-context mouth: full structured channel, bounded continuous prior.

## 2. Rules (C0–C8)

| ID | Rule |
|----|------|
| **C0** | Residual ledger is never capped for correctness. |
| **C1** | Denoise prior is capped: `HF_CAP = RESIDUAL_BLOCK * k` (default block=64, k=16 → 1024). |
| **C2** | Bulk write uses `learn_many` (one attractor flush), not `learn`×N, above threshold. |
| **C3** | At most one heavy Titanos+attractor instance in profile/seed jobs. |
| **C4** | Empty gate / none-channel ⇒ no invented facts. |
| **C5** | Empirical chat turns use tools / structured answer (chat-router). |
| **C6** | Hosted mouth is tools-only for world/user claims. |
| **C7** | Rank/φ contraction is explicit; undeclared conflation is a defect. |
| **C8** | Upscale only if scale probe meets `min_probe_hit_rate` and ops SLOs. |

Code: `src/resileos/capacity.py` (`CapacityConfig`, `hopfield_cap`, `should_use_learn_many`, `admit_scale`).

## 3. Constants

```text
RESIDUAL_BLOCK = 64
HF_CAP         = 64 * hf_cap_blocks   # default blocks=16 → 1024
PATTERN_DTYPE  = float32
require_learn_many_above = 256
min_probe_hit_rate = 1.0
```

`2048` on older patches is admissible as `64 * 32`; prefer naming via `hf_cap_blocks` so the bound tracks residual quanta, not a bare host number.

## 4. Relation to Frame Dimensionality Scale

| Dimensionality scale | Capacity contract |
|----------------------|-------------------|
| $D_{\mathrm{eff}}$, first-axis share | Optional **telemetry** on feature matrices (probe / residual) |
| Capacity ceiling $\log_2 k$ | Same form as gate capacity $\log_2\|\Sigma\|$ |
| Openness O1 abstention | C4 none-channel / recovery |
| Forced low-$D$ closed frame | C7 undeclared conflation; Eidolon-class *pattern*, not ideology scoring |
| Part 1 school catalog | Stays Human-Medium; not store relations |

Do not import atlas school axes into Titanos. Do use the same *idea*: many variables forced through a thin channel is a measurable structural event.

## 5. Wire points

| Component | Action |
|-----------|--------|
| `AttractorMemory.flush` | `max_hf = hopfield_cap()` |
| Seed / hub import | `learn_many` when `should_use_learn_many(n)` |
| `run_scale_profile` | Single instance; record hit_rate; `admit_scale` before recommending larger N |
| Chat router / hosted mouth | C4–C6 (docs already) |

## 6. Scale admission

```text
bands learn OK + hit_rate >= min_probe_hit_rate
  + (default path uses capped HF or deferred attractor)
  + RSS/latency within SLO
→ admit larger N or dim
```

Failure ⇒ do not upscale; raise `hf_cap_blocks` or host RAM only with a new report row.

## 7. One line

**Full residual channel; bounded prior; declared folds; no invent on empty gate — then scale.**
