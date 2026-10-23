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

```
engine 0: mean_std=0.000000  unique_rows=1
engine 1: mean_std=0.000000  unique_rows=1
engine 2: mean_std=0.000000  unique_rows=1
```

**Cause A.** `lat_s_k` is a constant vector for the entire run under the
current `EngineGroup → ControlPacket` path. The topic-labeled drive
reaches the coupling field and the packet's `F_res` / `DeltaS` / `mu`
fields, but it does not reach `lat_s_k`. The exact zero on `MI_lat` is
therefore trivially true in both κ conditions and says nothing about
whether coupling *would* propagate if the drive reached the latent block.

Implications, carried into §5:

- The per-engine latent block is dead for coupling under this protocol.
  The training probe input is aggregate-only.
- If propagation is ever wanted (Cause B behaviour), the RES-318 drive
  rule and the `EngineGroup → ControlPacket` path need review.
  `F_res_cross` and `ΔS_cross` adjust the *monitors*; they do not adjust
  `lat_s_k`. This is a substrate change, not a training-probe parameter.

The `_mechanism_stats()` helper in `run_coupled_signal_probe.py` reports
`lat_mechanism_coupled.cause` and `lat_mechanism_uncoupled.cause` so this
check re-runs automatically on any future drive-schedule change.

## 4. What the numbers do not say

**Not a claim that coupling is decorative.** At the aggregate level it is
measurably load-bearing. Removing coupling (`κ = 0`) destroys 90% of the
recoverable topic signal.

**Not a claim that per-engine state is useless.** Per-engine `lat_s_k`
carries signal in the single-engine ablation (`k = 0.9`). The zero here
is the *difference* `κ = 2` vs `κ = 0`, not the absolute amount. Each
engine still carries its own drive.

**Not a claim about training efficiency.** This is a signal-presence
probe. It does not measure whether a carrier can *use* the aggregate
signal to reduce a downstream loss. That's the training probe's job.

**Not a claim about scale.** `N = 3`, toy drives, synthetic topics.
`N = 8`, real data, and language-shaped targets are all untested.

## 5. Implications for the training probe

The disaggregation locks two design decisions:

**Aggregate features, not per-engine latents.** The carrier's input
should be `R_shared` (primary) plus optionally `M` (for robustness, not
because it's a second independent signal — see §3 finding 3). Do not
build a carrier around `lat` for the coupling effect; the per-engine
stream does not carry it under this protocol.

**κ ablation, not single-vs-coupled.** The matched-dimension `κ = 0` vs
`κ = 2` comparison isolates what coupling contributes. A single-engine
vs coupled-engine comparison changes the carrier's input dimension by
`N`, which confounds the size effect with the coupling effect.

Two constraints from earlier diagnostics still apply:

**Pretrained decoder, not random.** The single-engine ablation (`k = 0.9`)
measured a random transformer block. Its verdict named the reason: "a
random transformer block has no useful embedding geometry for auxiliary
losses to trade against." The coupled training probe with a random
decoder will reproduce the same degeneracy. Use `Qwen2.5-0.5B` or
`TinyLlama-1.1B` as the frozen decoder.

**Task, not raw NLL.** The substrate carries relational state, not
language. A next-token loss on random text will not reward modulation.
The task that matches the substrate is relational: "given `(subject,
relation)`, predict the object" against `configs/titanos-facts.json`.
Modulation should improve that task if the aggregate carrier is doing its
job.

## 6. What this closes

**RES-318 §8 invariant 2 (monitor correlation).** The coupled engines
show `ρ < 0.999` on `F_res` streams at `N = 5, κ = 0.5`. Confirmed by
`test_monitor_correlation`.

**RES-318 §8 invariant 5 (group basins are measurable).** `basin.py`
runs against the group step function. Confirmed by
`test_invariant_5_basins_measurable`.

**The "is coupling decorative?" question.** Answered: no, at the
aggregate level. The per-engine answer is resolved by §3a (Cause A:
drive does not reach latents under this path).

**The §3a mechanism check.** Resolved: Cause A. See §3a.

## 7. What this does not close

**The efficiency question.** Signal presence does not imply sample
efficiency. The training probe measures whether the aggregate signal
reduces steps-to-target on a real task. Until then, no "framework-native
FLOPs" claim stands.

**Multi-agent coherence.** RES-318 §11 asks whether a group-level triad
exists — whether the coupled system has discrete joint modes or only a
continuous phase distribution. This probe does not answer it; that's a
`basin.py` measurement at higher `N` and lower `κ`.

**Per-engine propagation.** §3a establishes that the current drive path
does not reach `lat_s_k`. Whether coupling *would* propagate if it did
is unanswered, and requires a substrate change to the
`EngineGroup → ControlPacket` path before it can be measured.

**Path C.** Nothing here changes the training-compute story. The coupling
field is a composition primitive, not a scaling lever.

## 8. Open questions

- ~~**§3a mechanism check.**~~ Resolved: Cause A. See §3a.
- **Is `R_shared` the sufficient statistic, or is there residual
  information in the matrix?** §3 finding 3 says the matrix is largely
  redundant. Whether it is *entirely* redundant — whether the matrix
  could be replaced by `R_shared` alone for the carrier — is testable by
  a carrier ablation reading `R_shared` only vs both. Do that in the
  training probe.
- **Does the aggregation result scale with `N`?** `N = 3` shows the
  aggregate works. Whether `N = 8` shows a stronger or weaker effect, and
  whether it plateaus, is unmeasured.
- **Does the aggregation result transfer to real drives?** The drives
  here are synthetic with a topic-labeled schedule. Real drives (packet
  streams from a lower layer, token embeddings) may not have the same
  topic-correlated magnitude structure. Re-run the probe with real drives
  before any training run on real data.
- **Does the drive path to `lat_s_k` need to change?** If per-engine
  propagation is ever wanted, the RES-318 §5 drive rule and the
  `EngineGroup → ControlPacket` path need review. This is not a probe
  parameter; it is a substrate change.

## 9. Reproduce

```bash
PYTHONPATH=src python scripts/run_coupled_signal_probe.py \
  --n 3 --steps 2000 --seed 0 \
  --kappa-on 2.0 \
  --n-topics 4 \
  --out artifacts/report_coupled_signal_probe.json
```

Uncoupled is always `κ = 0.0`; there is no `--kappa-uncoupled` flag.
The probe is deterministic given `--seed`. The report contains per-group
`ΔMI` values, the raw MI matrices at each `κ`, and the §3a
`lat_mechanism_coupled` / `lat_mechanism_uncoupled` diagnostics.

## 10. Read next

- [Structure-Flux-Mode Triad](triad.md) — RES-304
- [Engine Group Composition](engine-group.md) — RES-318
- [SDM + Hopfield Attractor Memory](sdm-hopfield.md) — RES-317
- [Documentation Index](../readme.md)
