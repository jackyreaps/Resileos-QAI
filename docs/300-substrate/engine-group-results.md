doc: RES-319
title: Engine Group Signal Probe Results
status: draft
depends_on: [RES-304, RES-318]
referenced_by: []

# Engine Group Signal Probe Results

The first measured result on the multi-engine composition. The question
RES-318 was built to answer: does correlated multi-stream state carry
task signal that a single engine cannot?

Result: yes, at the aggregate level. No, at the per-engine latent level.
The coupling field's order parameter `R_shared` carries ~89% of the
target entropy alone. Per-engine `lat_s_k` carries none.

This is a positive result for composition as a *signal source* and a
negative result for the "coupling creates new information inside each
engine" interpretation. Both are load-bearing for the training probe
design.

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

The probe runs the *same* `EngineGroup` configuration twice — once with
`κ = 2.0` (coupled) and once with `κ = 0.0` (uncoupled) — with the same
seeds, same drive schedule, same target labels. The only variable is
whether the coupling field's cross terms are active.

Feature groups extracted per step:

- **`lat_s_k`**: concatenation of each engine's latent vector (9
  dimensions total for `N = 3`, `r = 3`).
- **`R_shared`**: the coupling field's order parameter, a scalar in
  `[0, 1]`.
- **`coupling_matrix`**: the `(3, 3)` antisymmetric wrapped phase
  differences, flattened to 6 unique upper-triangle entries.

`ΔMI` is `MI(feature; topic)` at `κ = 2.0` minus the same at `κ = 0.0`.
Positive `ΔMI` means coupling creates signal; zero means coupling is
orthogonal to the target; negative means coupling destroys signal.

## 2. Results

| Feature group | `ΔMI` (nats) | % of `H(topic)` |
|---|---|---|
| per-engine `lat_s_k` | ~0 | ~0% |
| `R_shared` | **+1.24** | **~89%** |
| `coupling_matrix` | +1.13 | ~82% |

The `~0` on `lat_s_k` is within estimator noise at `T = 2000` and
`k = 8`. The `+1.24` and `+1.13` are far above the noise floor for
these parameters.

## 3. What the numbers say

**Finding 1 — coupling carries task signal at the aggregate level.**
`R_shared` alone recovers ~89% of the topic entropy. This is not a
constant bias: at `κ = 0`, uncoupled engines start at random phases and
the order parameter stays near `1/sqrt(N)`; at `κ = 2`, the field
synchronizes toward a mean phase that reflects the drive statistics,
and the topic label is encoded in those statistics. The `ΔMI` is the
difference between the two regimes.

**Finding 2 — coupling does not propagate into per-engine latents.**
This is the important negative result. If coupling propagated — if
engine `i`'s state ended up reflecting information from engine `j`'s
drive — `lat_s_k` would show `ΔMI > 0`. It shows ~0. The cross terms
from RES-318 §5 (`F_res_cross`, `ΔS_cross`, `μ` XOR) adjust each
engine's *drive*, but the resulting packet latents do not carry
information about the other engines' topics.

The interpretation: the coupling field is a shared *aggregate*, not a
communication channel. Engines synchronize to a common phase, and the
common phase encodes the drive mean. But engine `i`'s internal state
after sync does not contain anything specific to engine `j`.

**Finding 3 — `R_shared` and `coupling_matrix` are not independent.**
Both show `ΔMI > 1.1` nats, but `H(topic)` is only 1.386. Two
independent channels would sum past the entropy ceiling. They measure
overlapping information: the phase distribution's aggregate and its
pairwise detail. `R_shared` is the sufficient statistic; the full
matrix is largely redundant for topic prediction.

## 4. What the numbers do not say

**Not a claim that coupling is decorative.** At the aggregate level it
is measurably load-bearing. Removing coupling (`κ = 0`) destroys 89%
of the recoverable topic signal.

**Not a claim that per-engine state is useless.** Per-engine `lat_s_k`
carries signal in the single-engine ablation. The `~0` here is the
*difference* `κ = 2` vs `κ = 0`, not the absolute amount. Each engine
still carries its own drive.

**Not a claim about training efficiency.** This is a signal-presence
probe. It does not measure whether a carrier can *use* the aggregate
signal to reduce a downstream loss. That's the training probe's job.

**Not a claim about scale.** `N = 3`, toy drives, synthetic topics.
`N = 8`, real data, and language-shaped targets are all untested.

## 5. Implications for the training probe

The disaggregation locks two design decisions:

**Aggregate features, not per-engine latents.** The carrier's input
should be `R_shared` (primary) plus optionally `coupling_matrix`
(for robustness, not because it's a second independent signal — see
§3 finding 3). Do not build a carrier around `lat_s_k` for the
coupling effect; the per-engine stream does not carry it under this
protocol.

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
aggregate level; yes, at the per-engine level.

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
  the same topic-correlated magnitude structure. The probe should be
  re-run with real drives before any training run on real data.
- **Is the `lat_s_k` null result stable across seeds?** One seed
  (`seed = 0`). The `+1.24` is well above noise, but the `~0` could be
  a small positive value masked by estimator noise. Re-run with
  `seed ∈ {1, 2, 3}` before concluding propagation is *zero* as
  opposed to *negligible*.

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
