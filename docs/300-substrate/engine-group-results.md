doc: RES-319
title: Engine Group Signal Probe Results
status: draft
depends_on: [RES-304, RES-318]
referenced_by: []

# Engine Group Signal Probe Results

The first measured result on the multi-engine composition. The question
RES-318 was built to answer: does correlated multi-stream state carry
task signal that a single engine cannot?

Result: yes, at the aggregate level. No, at the per-engine latent level
— with a caveat about whether the drive schedule reaches latents at all
(§3a).

This is a positive result for composition as a *signal source* and a
negative result for the "coupling creates new information inside each
engine" interpretation under the current drive schedule. Both are
load-bearing for the training probe design.

## 1. Setup

| Parameter | Value |
|---|---|
| Engines | `N = 3` |
| Steps | `T = 2000` |
| Seed | `0` |
| Coupling strength | `κ = 2.0` (coupled) vs `κ = 0.0` (uncoupled) |
| Drive schedule | topic-labeled; topics drive which phase region each engine enters |
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
- **`R_shared`**: the coupling field's order parameter, a scalar in
  `[0, 1]`.
- **`M`**: the antisymmetric coupling matrix, flattened to unique
  entries.

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
uncoupled runs return `MI = 0.0` to the full precision of the
estimator. See §3a.

The `ΔMI = +0.185` in the last row is the aggregate feature-vector
delta, not a per-dimension average. It is smaller than `R_shared`'s
solo `+1.243` because the aggregate vector includes the zero-`MI`
latent block, which dilutes the total.

## 3. What the numbers say

**Finding 1 — coupling carries task signal at the aggregate level.**
`R_shared` alone recovers ~90% of the topic entropy. At `κ = 0`,
uncoupled engines start at random phases and the order parameter stays
near `1/sqrt(N)`; at `κ = 2`, the field synchronizes toward a mean
phase that reflects the drive statistics, and the topic label is
encoded in those statistics. The `ΔMI` is the difference between the
two regimes.

**Finding 2 — coupling does not propagate into per-engine latents
under this drive schedule.** This is the important negative result.
If coupling propagated — if engine `i`'s state ended up reflecting
information from engine `j`'s drive — `lat` would show `ΔMI > 0`.
It shows `ΔMI = 0.000` exactly. The cross terms from RES-318 §5
(`F_res_cross`, `ΔS_cross`, `μ` XOR) adjust each engine's *drive*, but
the resulting packet latents do not carry information about the topic.

**Finding 3 — `R_shared` and `M` are not independent.** Both show
`ΔMI > 1.1` nats, but `H(topic)` is only 1.386. Two independent
channels would sum past the entropy ceiling. They measure overlapping
information: the phase distribution's aggregate and its pairwise
detail. `R_shared` is the sufficient statistic; the full matrix is
largely redundant for topic prediction.

## 3a. The exact-zero on `lat` needs a mechanism check

`MI_lat_coupled = 0.0` and `MI_lat_uncoupled = 0.0`, both to full
precision. Exactly zero from a 2000-sample histogram is unusual — a
true null result under noise typically gives `~0.001` to `~0.01`, not
`0.0`. Two mechanisms can produce the exact zero:

**Cause A — drive schedule does not reach latents.** If the topic-
labeled drives enter only `CouplingField.step(drives=...)` and never
reach each engine's W matrix or the core's internal state, then
`lat_s_k` is invariant to topic by construction. The null result is
then trivially true in both κ conditions and says nothing about
whether coupling *would* propagate if the drive were richer.

**Cause B — latents vary but are independent of topic.** If the
drives reach the core and `lat_s_k` varies across steps but is
statistically independent of the topic label, the exact zero is a
real, strong negative result.

The distinguishing test:

    lat_arr = np.array(lat_streams)   # (T, N, r)
    for i in range(N):
        std = lat_arr[:, i, :].std(axis=0)
        uniq = len(np.unique(lat_arr[:, i, :], axis=0))
        print(f"engine {i}: std={std}, unique_rows={uniq}")

| `std` | `unique_rows` | Reading |
|---|---|---|
| ~0 | 1 | Cause A. Latents constant. Drive does not reach them. |
| > 0 | ~`T` | Cause B. Latents vary but uncorrelated with topic. |
| > 0 | ~4 | Cluster by topic. Probe bug (MI computation or bin count). |

**This test has not been run.** Until it is, "Finding 2" should be
read as *"under the current drive schedule, per-engine latents show
no measurable topic signal,"* not as a general statement about
propagation.

## 4. What the numbers do not say

**Not a claim that coupling is decorative.** At the aggregate level it
is measurably load-bearing. Removing coupling (`κ = 0`) destroys 90%
of the recoverable topic signal.

**Not a claim that per-engine state is useless.** Per-engine `lat_s_k`
carries signal in the single-engine ablation (`k = 0.9`). The zero
here is the *difference* `κ = 2` vs `κ = 0`, not the absolute amount.
Each engine still carries its own drive.

**Not a claim about training efficiency.** This is a signal-presence
probe. It does not measure whether a carrier can *use* the aggregate
signal to reduce a downstream loss. That's the training probe's job.

**Not a claim about scale.** `N = 3`, toy drives, synthetic topics.
`N = 8`, real data, and language-shaped targets are all untested.

## 5. Implications for the training probe

The disaggregation locks two design decisions:

**Aggregate features, not per-engine latents.** The carrier's input
should be `R_shared` (primary) plus optionally `M` (for robustness,
not because it's a second independent signal — see §3 finding 3). Do
not build a carrier around `lat` for the coupling effect; the
per-engine stream does not carry it under this protocol.

**κ ablation, not single-vs-coupled.** The matched-dimension
`κ = 0` vs `κ = 2` comparison isolates what coupling contributes.
A single-engine vs coupled-engine comparison changes the carrier's
input dimension by `N`, which confounds the size effect with the
coupling effect.

Two constraints from earlier diagnostics still apply:

**Pretrained decoder, not random.** The single-engine ablation
(`k = 0.9`) measured a random transformer block. Its verdict named the
reason: "a random transformer block has no useful embedding geometry
for auxiliary losses to trade against." The coupled training probe
with a random decoder will reproduce the same degeneracy. Use
`Qwen2.5-0.5B` or `TinyLlama-1.1B` as the frozen decoder.

**Task, not raw NLL.** The substrate carries relational state, not
language. A next-token loss on random text will not reward
modulation. The task that matches the substrate is relational:
"given `(subject, relation)`, predict the object" against
`configs/titanos-facts.json`. Modulation should improve that task if
the aggregate carrier is doing its job.

## 6. What this closes

**RES-318 §8 invariant 2 (monitor correlation).** The coupled engines
show `ρ < 0.999` on `F_res` streams at `N = 5, κ = 0.5`. Confirmed by
`test_monitor_correlation`.

**RES-318 §8 invariant 5 (group basins are measurable).** `basin.py`
runs against the group step function. Confirmed by
`test_invariant_5_basins_measurable`.

**The "is coupling decorative?" question.** Answered: no, at the
aggregate level. The per-engine answer is pending the §3a mechanism
check.

## 7. What this does not close

**The efficiency question.** Signal presence does not imply sample
efficiency. The training probe measures whether the aggregate signal
reduces steps-to-target on a real task. Until then, no
"framework-native FLOPs" claim stands.

**Multi-agent coherence.** RES-318 §11 asks whether a group-level
triad exists — whether the coupled system has discrete joint modes or
only a continuous phase distribution. This probe does not answer it;
that's a `basin.py` measurement at higher `N` and lower `κ`.

**Path C.** Nothing here changes the training-compute story. The
coupling field is a composition primitive, not a scaling lever.

## 8. Open questions

- **§3a mechanism check.** Does the drive schedule reach `lat_s_k` at
  all? Run the std/unique-rows diagnostic before treating Finding 2
  as a general propagation result.
- **Is `R_shared` the sufficient statistic, or is there residual
  information in the matrix?** §3 finding 3 says the matrix is largely
  redundant. Whether it is *entirely* redundant — whether the matrix
  could be replaced by `R_shared` alone for the carrier — is testable
  by a carrier ablation reading `R_shared` only vs both. Do that in
  the training probe.
- **Does the aggregation result scale with `N`?** `N = 3` shows the
  aggregate works. Whether `N = 8` shows a stronger or weaker effect,
  and whether it plateaus, is unmeasured.
- **Does the aggregation result transfer to real drives?** The drives
  here are synthetic with a topic-labeled schedule. Real drives
  (packet streams from a lower layer, token embeddings) may not have
  the same topic-correlated magnitude structure. Re-run the probe with
  real drives before any training run on real data.
- **Is `MI_lat = 0.0` stable across seeds?** One seed (`seed = 0`). If
  the §3a diagnostic shows latents vary (Cause B), re-run with
  `seed ∈ {1, 2, 3}` to confirm the zero is a stable finding, not a
  single-seed artifact.

## 9. Reproduce

    PYTHONPATH=src python scripts/run_coupled_signal_probe.py \
        --n-engines 3 --steps 2000 --seed 0 \
        --kappa-coupled 2.0 --kappa-uncoupled 0.0 \
        --n-topics 4 \
        --out artifacts/report_coupled_signal_probe.json

The report contains per-group `ΔMI` values and the raw MI matrices at
each `κ`. The probe is deterministic given `--seed`.

## 10. Read next

- [Structure-Flux-Mode Triad](triad.md) — RES-304
- [Engine Group Composition](engine-group.md) — RES-318
- [SDM + Hopfield Attractor Memory](sdm-hopfield.md) — RES-317
- [Documentation Index](../readme.md)
