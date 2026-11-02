---
doc: RES-330
title: Capacity Contract
status: proposed
depends_on: [RES-317, RES-320, RES-327-gate, RES-401]
related_to: [scale-decision-2k5k, growth-spine, frame-atlas-bridge]
---

# Capacity Contract

## 1. Intent

Before upscaling N, dim, or GPU, the system runs under **named bounds**:

- The **residual ledger** (bands / facts / SDM writes) stays complete.
- The **denoise prior** (Hopfield) and the **speech channel** (gate / mouth) stay capacity-bounded.
- Contraction is **declared** (φ-compress, bulk flush, HF cap), not silent loss of axes.

Same construction as a minimum-parameter / short-context mouth: full structured channel, bounded continuous prior.

## 2. Rules (C0–C8)

| ID | Rule |
|----|------|
| **C0** | Residual ledger is never capped for correctness. |
| **C1** | Denoise prior is capped: `HF_CAP = RESIDUAL_BLOCK * k` (default block=64, k=16 → 1024). |
| **C2** | Bulk write uses `learn_many` (one attractor flush), not `learn`×N, above threshold. |
| **C3** | At most one heavy Titanos+attractor instance in profile/seed jobs. |
| **C4** | Empty gate / none-channel ⇒ no invented facts. |
| **C5** | Empirical chat turns use tools / structured answer (chat-router). |
| **C6** | Mouth is tools-only for world/user claims. |
| **C7** | Rank/φ contraction is explicit; undeclared conflation is a defect. |
| **C8** | Upscale only if scale probe meets `min_probe_hit_rate` and ops SLOs. |

Code: `src/resileos/capacity.py`.

## 3. Constants

```text
RESIDUAL_BLOCK = 64
HF_CAP         = 64 * hf_cap_blocks   # default blocks=16 → 1024
PATTERN_DTYPE  = float32
require_learn_many_above = 256
min_probe_hit_rate = 1.0
```

## 4. Operating metrics (apply now)

These are the metrics that matter **before** any personified surface. They
are ordinary product telemetry, not a third-party dependency.

| Metric | Definition | Target sense |
|--------|------------|--------------|
| **M1 tool adherence** | On turns classified TOOL_FACT / HUB_RECALL, fraction that issued a tool/structured call before asserting a fact | → 1.0 |
| **M2 invent rate** | Assertions of world/user fact after empty rows / NONE_CHANNEL / ABSTAINED | → 0 |
| **M3 store hit rate** | Probe queries with known triples return correct objects | ≥ `min_probe_hit_rate` |
| **M4 hub durability** | Hub triples survive restart/load | retained |
| **M5 soft-chat purity** | SOFT_CHAT turns that introduce unbacked empirical claims | → 0 |
| **M6 bulk write policy** | Seeds/imports with N ≥ threshold use `learn_many` | 100% |
| **M7 prior bound** | Hopfield rebuild rows ≤ `HF_CAP` | always |
| **M8 admit** | Scale-up only when M3 + latency/RSS SLO hold | enforced |

M1–M2–M5 are the same *kind* of discipline good real-time agents need (tool
adherence over fluent invention). Implement them on **text** router + tools
first.

## 5. Relation to dimensionality instrument

| Dimensionality scale | Capacity contract |
|----------------------|-------------------|
| Capacity ceiling $\log_2 k$ | Gate capacity $\log_2\|\Sigma\|$ |
| O1 abstention | C4 / M2 |
| Forced low-$D$ closed frame | C7 undeclared conflation |
| $D_{\mathrm{eff}}$ | Optional offline telemetry — not ideology scoring |

## 6. Wire points

| Component | Action |
|-----------|--------|
| `AttractorMemory.flush` | `max_hf = hopfield_cap()` |
| Seed / hub import | `learn_many` when `should_use_learn_many(n)` |
| `run_scale_profile` | Single instance; record hit_rate; `admit_scale` |
| Chat router / text mouth | M1, M2, M5 |

## 7. Scale admission

```text
M3 + bands learn under SLO + (capped HF or deferred attractor) + RSS OK
→ admit larger N or dim
```

## 8. One line

**Full residual channel; bounded prior; declared folds; measure tool honesty before upscale or surface polish.**
