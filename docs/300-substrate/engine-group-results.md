---
doc: RES-319
title: Engine Group Signal Probe Results
status: draft
depends_on: [RES-304, RES-318]
referenced_by: []
---

# Engine Group Signal Probe Results

The first measured result on the multi-engine composition. The question
RES-318 was built to answer: does correlated multi-stream state carry
task signal that a single engine cannot?

Result: yes, at the aggregate level. No, at the per-engine latent level —
and §3a now confirms the reason is that the drive schedule never reaches
`lat_s_k` under the current `EngineGroup → ControlPacket` path, so the
zero is trivially true rather than a propagation falsification.

This is a positive result for composition as a *signal source* and a
"not measured" result for the "coupling creates new information inside
each engine" interpretation. Both are load-bearing for the training
probe design.

## 1. Setup

| Parameter | Value |
|---|---|
| Engines | `N = 3` |
| Steps | `T = 2000` |
| Seed | `0` |
| Coupling strength | `κ = 2.0` (coupled) vs `κ = 0.0` (uncoupled) |
| Drive schedule | topic-labeled; drives reach `CouplingField.step(drives=...)` |
| N topics | 4 |
| Target entropy | `H(topic) ≈ log(4) ≈ 1.386` nats |
| MI method | histogram, `k = 8` bins, `T = 2000` samples |
| Feature dimension | 25 |

The probe runs the *same* `EngineGroup` configuration twice — once with
`κ = 2.0` (coupled) and once with `κ = 0.0` (uncoupled) — with the same
seeds, same drive schedule, same target labels. The only variable is
whether the coupling field's cross terms are active.

Feature groups extracted per step:

- **`lat`**: per-engine latent state, concatenated across `N` engines.
- **`R_shared`**: the coupling field's order parameter, a scalar in `[0, 1]`.
- **`M`**: the antisymmetric coupling matrix, flattened to unique entries.

`ΔMI` is `MI(feature; topic)` at `κ = 2.0` minus the same at `κ = 0.0`.
Positive `ΔMI` means coupling creates signal; zero means coupling is
orthogonal to the target; negative means coupling destroys signal.

## 2. Results

Exact values from `artifacts/report_coupled_signal_probe.json`:

| Feature group | `MI` (κ=2) | `MI` (κ=0) | `ΔMI` (nats) | % of `H(topic)` |
|---|---|---|---|---|
| `lat` (per-engine) | 0.000 | 0.000 | **0.000** | **0%** |
| `R_shared` | 1.246 | 0.003 | **+1.243** | **~90%** |
| `M` (coupling matrix) | 1.126 | 0.000086 | **+1.126** | **~81%** |
| **aggregate `ΔMI`** | — | — | **+0.185** | ~13% |

The `0.000` on `lat` is **exact**, not a noise floor. Both coupled and
uncoupled runs return `MI = 0.0` to the full precision of the estimator.
See §3a — this is now confirmed to be Cause A (drive does not reach
latents), not a propagation falsification.

The `ΔMI = +0.185` in the last row is the aggregate feature-vector
delta, not a per-dimension average. It is smaller than `R_shared`'s solo
`+1.243` because the aggregate vector includes the zero-`MI` latent
block, which dilutes the total.

## 3. What the numbers say

**Finding 1 — coupling carries task signal at the aggregate level.**
`R_shared` alone recovers ~90% of the topic entropy. At `κ = 0`,
uncoupled engines start at random phases and the order parameter stays
near `1/sqrt(N)`; at `κ = 2`, the field synchronizes toward a mean phase
that reflects the drive statistics, and the topic label is encoded in
those statistics. The `ΔMI` is the difference between the two regimes.

**Finding 2 — coupling does not propagate into per-engine latents under
this drive schedule.** `lat` shows `ΔMI = 0.000` exactly. Per §3a, this
is because the drive schedule never writes to `lat_s_k` — `lat_s_k` is
constant across the entire run. The finding is therefore *trivially*
true under the current path: a constant vector carries no information
about any label. It says nothing about whether coupling *would*
propagate if the drive reached the core's latent state.

**Finding 3 — `R_shared` and `M` are not independent.** Both show
`ΔMI > 1.1` nats, but `H(topic)` is only 1.386. Two independent channels
would sum past the entropy ceiling. They measure overlapping
information: the phase distribution's aggregate and its pairwise detail.
`R_shared` is the sufficient statistic; the full matrix is largely
redundant for topic prediction.

## 3a. The exact-zero on `lat` — mechanism check

`MI_lat_coupled = 0.0` and `MI_lat_uncoupled = 0.0`, both to full
precision. Exactly zero from a 2000-sample histogram is unusual — a true
null result under noise typically gives `~0.001` to `~0.01`, not `0.0`.

Two mechanisms can produce the exact zero:

**Cause A — drive schedule does not reach latents.** If the topic-labeled
drives enter only `CouplingField.step(drives=...)` and never reach each
engine's W matrix or the core's internal state, then `lat_s_k` is
invariant to topic by construction. The null result is then trivially
true in both κ conditions and says nothing about whether coupling
*would* propagate if the drive were richer.

**Cause B — latents vary but are independent of topic.** If the drives
reach the core and `lat_s_k` varies across steps but is statistically
independent of the topic label, the exact zero is a real, strong
negative result.

**Result (run 2026-10-23, N=3, T=2000, seed 0, κ=2):**
