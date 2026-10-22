doc: RES-502
title: Hardened Implementation Roadmap
status: draft
depends_on: [RES-313, RES-315, RES-501]
referenced_by: []

# Hardened Implementation Roadmap

Version-gated plan from the current baseline to a sparse MoE architecture.
Every compute projection below is conditional on a single measured number
from §1.1. Until that number exists, the v2.0.0 section is a sketch, not
a plan.

## 1.0.x — Baseline grounding and sequential mechanics

### 1.1 The load-bearing ablation — BLOCKING

`scripts/run_efficiency_ablation.py` measures three k factors:

| Factor | Definition | Reliability |
|---|---|---|
| `k_steps` | steps_NLL / steps_framework | Reliable at toy scale |
| `k_flops_est` | total_flops_NLL / total_flops_framework | Analytic; use for projections |
| `k_wall_toy` | wall_NLL / wall_framework | Python-bound; trends to 1.0; do not use |

Target accuracy is fixed before the run: `target_nll = baseline_nll − Δ`,
where `baseline_nll` is the no-modulation decoder on the held-out set.
Δ defaults to 0.05.

**Three outcomes, all written down before the run:**

| `k_flops_est` | Verdict | Consequence |
|---|---|---|
| ≥ 3 | viable | v2.0.0 proceeds |
| 1 < k < 3 | marginal | savings do not justify framework complexity; v2.0.0 on hold |
| ≤ 1 | falsified | framework-native objective is not a scaling lever; revert to MoE-only |

`k ≤ 1` is a first-class result, not a failure to be explained away. If the
ablation returns it, §4 is deleted from the roadmap and the project pivots.

### 1.2 Sequential chain retention

Multi-hop `chain` stays strictly sequential. Parallel unfolding is removed
as a milestone and reclassified as long-term research: at `dim = 10,000`
the capacity bound `dim ≥ 2 · n_candidates · log(dim)` leaves no room for
parallel fan-out. Sequential unbinding plus cleanup is the only viable
path at this scale.

## 1.1.0 — Attractor memory layer (parallel to 1.0.x)

Mitigates hypervector cross-talk during multi-step sequential unrolling.

### 2.1 Kanerva SDM + Hopfield relaxation

`src/resileos/substrate/sdm.py`:

- Static sparse address matrix (Kanerva 1988) as a discrete attractor web.
- Noisy unbound vectors map to nearest sparse coordinates.
- Continuous Hopfield relaxation (Ramsauer et al. 2020) snaps them back to
  deterministic concept boundaries.
- Zero trainable parameters.

**Gate to 1.2.0:** SDM + Hopfield must show measurable crosstalk reduction
on a chain benchmark versus raw cleanup. If it does not, 1.2.0 does not
start. This gate is new and is the reason 1.2.0 is not unconditional.

## 1.2.0 — Structural refinements

### 3.1 Unitary binding

Bipolar ±1 bind is already exactly norm-preserving. The work here is
verification, not adding orthogonality:

- Measure unbind recovery rate against the theoretical exponential decay
  over chain depth.
- If the measured rate is worse than theory, switch to FFT circular
  convolution (exactly unitary) and re-measure.

This is a 20-line change plus a benchmark, not an architecture change.

### 3.2 Sector-bus realignment

Reframed honestly: the sector bus does **not** bypass database complexity
for exact lookups. It provides soft boundaries, graceful degradation under
loss, and compositional keys, at the cost of requiring a traditional hash
index past ~10³ sectors.

Implementation: partition the Titanos store into relation bands. This
formalises sector partitioning as an extension of the existing
`_bands` layout.

## 2.0.0 — Sparse MoE with VSA routing (conditional on 1.1)

**Do not start until `k_flops_est` is measured.** The numbers below are
projections under a specific assumption about `k`.

### 4.1 Sparsity, not VSA math

Per-token compute reduction comes from MoE sparsity, not from VSA. A
1T-parameter model as 100 experts, ~10B active per token, locks
backprop at ~6 × 10¹⁰ FLOPs per step.

### 4.2 Dual-mode router

1. **Fixed sectors** — pre-defined orthogonal VSA signatures for
   structured Titanos packets. O(1) amortised hash lookup + O(1) dispatch.
2. **Learned sectors** — standard learned linear gate for raw text.

Note: fixed-sector routing is O(1) *after* the hash lookup, and the hash
lookup itself is O(1) amortised. It does not bypass the index.

### 4.3 Decoupled levers

| Lever | Managed by | Effect |
|---|---|---|
| FLOPs per token | MoE sparsity | 1T dense → ~1.2 × 10²⁴ FLOPs for 20T tokens |
| Sample efficiency | Framework-native data pipeline | Divided by `k_flops_est` |

### 4.4 Hardware interface only

The quantum / coherence backend is a hardware interface specification, not
an implementation milestone. It documents input/output contracts for a
future optical or quantum dot-product backend. No code.

## The scaling equation

    Total compute = (1.2 × 10²⁴ × (1 + D)) / k_flops_est

where `D` is the production data-generation cost as a fraction of training
cost. `D` is not measured by the toy ablation and must be estimated from
the real `ResidualCore` data pipeline before any projection is quoted.

| `k_flops_est` | `D` | Total FLOPs | Hardware profile |
|---|---|---|---|
| 1 | 0 | 1.2 × 10²⁴ | ~10,000 H100 × 4.5 d (~$15M) |
| 1 | 1 | 2.4 × 10²⁴ | ~20,000 H100 × 4.5 d |
| 10 | 0 | 1.2 × 10²³ | ~1,000 H100 × 1 wk |
| 10 | 1 | 2.4 × 10²³ | ~2,000 H100 × 1 wk |
| 100 | 0 | 1.2 × 10²² | ~100 H100 × few d |
| 100 | 1 | 2.4 × 10²² | ~200 H100 × few d |

Add 20% wall-clock margin for sharding infrastructure (FSDP/ZeRO overhead)
on every row.

## What this roadmap does not claim

- That `k_flops_est` measured at toy scale transfers to 1T scale. It may
  rise (more capacity per example) or fall (large models already extract
  the signal). An intermediate-scale check at ~1B is required before the
  1,000-H100 run is committed.
- That the attractor memory layer substitutes for the MoE work. It does
  not; it is a parallel track.
- That a successful SDM + Hopfield layer implies the MoE router will work.
- That the sector bus eliminates lookup cost. It does not.

## Read next

- [Roadmap](roadmap.md) — RES-501
- [Capacity Law](../310-hierarchy/capacity-law.md) — RES-313
- [Modulation Interface](../310-hierarchy/modulation-interface.md) — RES-315
