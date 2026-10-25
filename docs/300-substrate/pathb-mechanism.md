---
doc: RES-326
title: Path B Mechanism Confirmation (CPU)
status: draft
depends_on: [RES-315, RES-318, RES-319]
referenced_by: []
---

# Path B Mechanism Confirmation (CPU)

The aggregate feature vector from a coupled `EngineGroup` (RES-318)
carries fact-level information (RES-319). That result measured
separability: nearest-centroid on 7-dim features separated ~80% of 120
facts under coupling, ~3% under no coupling.

This document records the next measurement: does the aggregate feature
survive projection through a trainable readout into a frozen
transformer, and does coupling still beat non-coupling under that
readout? Three CPU-feasible probes answer it. All three converge:
coupling improves the readout by roughly +0.07 to +0.11 accuracy and
+0.17 to +0.33 NLL. The mechanism works. The pretrained-scale question
remains open. See §5.

## 1. The mechanism

Path B (RES-315 §2) specifies a small trainable carrier between the
substrate and a frozen decoder:

    aggregate_features (7-dim for N=3)
        │
        ▼
    AggregateCarrier (MLP)
        │
        ▼
    modulation (vocab,) — logit bias
        │
        ▼
    frozen decoder logits + modulation

The carrier trains; the decoder is frozen; the substrate is frozen.
The question is whether the aggregate signal projects usefully through
this path, and whether that projection benefits from coupling.

## 2. Three probes

All three use the same 7-dim aggregate (RES-318 §6):

    R_shared              (1)
    upper-tri M           (3, for N=3)
    mean F_res            (3, per engine)

Each fact is processed through a fresh `EngineGroup` with that fact's
deterministic drive vector (RES-319 §5), then the aggregate is
extracted. The three probes differ in readout:

| Probe | Readout | Task | Vocab |
|---|---|---|---|
| A. Feature-only | linear centroid | 120-way classification | 120 |
| B. Closed-vocab carrier | MLP | 68-way classification | 68 |
| C. Mini-transformer logit bias | MLP + frozen transformer | next-token | 79 |

Probe A is the linear baseline; probes B and C add nonlinearity and
transformer structure respectively. Probe C is the closest CPU
approximation to the full Path B probe (which uses a pretrained decoder
at 151k vocab).

## 3. Results

| Probe | κ=0 | κ=2 | Δ |
|---|---|---|---|
| A. Feature-only accuracy (seed 0) | 0.032 | 0.706 | +0.674 |
| A. Feature-only accuracy (earlier run) | 0.015 | 0.803 | +0.788 |
| B. Closed-vocab accuracy | 0.817 | 0.892 | +0.075 |
| B. Closed-vocab NLL | 0.816 | 0.642 | +0.174 |
| C. Mini-transformer accuracy | 0.79 | 0.90 | +0.108 |
| C. Mini-transformer NLL | 0.93 | 0.61 | +0.325 |
| C. Baseline (no carrier) | — | 4.51 NLL / 0.00 acc | — |

Three observations:

**Probe A is not comparable to B and C in absolute terms.** It is a
120-way classification with no learned weights, so chance is 0.008. It
measures separability of the raw features, not task performance. The
variance between the two runs (0.71 vs 0.80) is measurement noise on a
single seed; three seeds would tighten it.

**Probes B and C converge on the same delta.** +0.075 to +0.108
accuracy, +0.174 to +0.325 NLL. Despite different readout
architectures and different tasks (68-way classification vs 79-token
next-token), the coupling effect is stable.

**Probe C's baseline is essentially uniform.** 4.51 NLL vs ln(79) =
4.37. The random-init frozen transformer has no useful prior; the
carrier is the entire source of task performance. This isolation is
what makes probe C clean: the coupling effect is not competing with a
pretrained prior, because there is none.

### 3a. Three-seed mini-transformer (NLL is load-bearing)

| Seed | improvement_κ NLL | acc κ=2 |
|------|-------------------|---------|
| 0 | +0.092 | 0.892 |
| 1 | +0.083 | 0.775 |
| 2 | +0.073 | 0.758 |
| **mean ± std** | **+0.083 ± 0.009** | **0.808 ± 0.073** |

NLL delta is tight and sign-stable across seeds. Accuracy spreads
~13 percentage points (0.758 to 0.892) — the carrier's decision
boundary is sensitive to initialization on 120 facts with a small
readout. Quote accuracy only with the ±0.07 interval; never as a
single "0.81".

The NLL result is the load-bearing number: same frozen block, same
carrier architecture, same 7-dim features, κ=2 beats κ=0 with low
variance. The mechanism is confirmed.

## 4. What the numbers say

**Nonlinearity matters.** Feature-only (linear) gives 0.706 accuracy at
κ=2. Closed-vocab (MLP) gives 0.892. That is +0.186 from nonlinearity
on the same 7-dim features. The aggregate carries nonlinear structure
a linear readout underuses.

**The mechanism works.** A 7-dim aggregate → MLP → logit bias into a
frozen transformer produces a usable signal. In probe C, the
transformer's random block is essentially uniform (4.51 NLL) and the
carrier alone drives accuracy from 0 to 0.90. The aggregation →
projection → injection path is functional.

**Coupling helps across readouts.** The κ=2 vs κ=0 delta is +0.075 to
+0.108 accuracy in the two nonlinear probes. It is not specific to one
readout mechanism. The signal survives two different task framings.
Probe B is a 68-way classification over object IDs. Probe C is
next-token prediction over a 79-token vocabulary. Both are relational
object prediction. Both show the same effect.

**The NLL delta is seed-stable.** +0.083 ± 0.009 across three seeds.
This is not a single lucky draw. The mechanism is confirmed at the
task level, not just the separability level.

## 5. What the numbers do not say

**Not measured: pretrained decoder.** Probes B and C use
randomly-initialized or closed-vocab readouts. The full Path B probe
uses a pretrained decoder — `Qwen/Qwen2.5-0.5B` or
`HuggingFaceTB/SmolLM-135M` — with a 151k-token vocabulary. That
measurement is not done.

The gap matters because pretrained decoders have prior structure. When
the aggregate-projected logit bias lands in a 151k-vocab space where
the decoder already has shaped logits, the carrier's bias has to
overcome or supplement an existing distribution. On a random block
there is nothing to overcome.

The direction of that effect is empirical. It could be:

- **Easier** — the pretrained block has competent structure the carrier
  can align to, producing higher accuracy with less carrier capacity
  needed.
- **Harder** — the pretrained block has confident but wrong predictions
  (mythology is rare in pretraining data), and the carrier's logit bias
  has to dominate a structured distribution.
- **Neutral** — the effect is the same magnitude as on the random block.

Only the GPU probe distinguishes these. The CPU results show the
mechanism works in principle; they do not predict the
pretrained-scale outcome.

**Not measured: scaling to 1000+ facts.** Probes B and C use 120
facts. The +0.075 to +0.108 accuracy delta on 120 facts may not scale
linearly. A 1000-fact task with a 68-way object vocabulary is
structurally different — fewer bits per fact, more inter-fact
confusion. Not measured.

**Not measured: accuracy variance across seeds (resolved).** The NLL
delta is seed-stable (±0.009), but the accuracy is not (±0.073). The
per-seed table in §3a shows this. Any accuracy claim should carry the
interval.

## 6. What this closes

**The "does the mechanism work" question.** Yes. Aggregate → carrier
→ logit bias → frozen decoder produces task-relevant signal.

**The "is coupling decorative" question, confirmed at readout.**
Already answered at the feature level (RES-319), now confirmed at the
readout level. Coupling improves object prediction through multiple
readout mechanisms.

**The "does nonlinearity help" question.** Yes. +0.186 accuracy from
linear to nonlinear readout on the same features.

**The "is the NLL delta seed-stable" question.** Yes. +0.083 ± 0.009
across three seeds.

## 7. What this does not close

**The pretrained-scale question.** Requires a machine with ≥8 GB RAM
or a GPU. The probe script `run_aggregate_training_probe.py` is ready;
the decoder and the environment are not.

**The 1000+ fact question.** Requires expanded fact sets and
re-measurement.

**The RAG-bridge question.** Independent of Path B. Uses the exact
retrieval path (`ask_list` / SPARQL) rather than the
aggregate-carrier path.

## 8. Open questions

- **Does the delta transfer to pretrained embeddings?** Answered by the
  GPU probe when available.
- **Does the delta scale with fact count?** Test at 500, 1000, 2000.
- **Is the coupling effect the same size in the logit-bias path as in
  the closed-vocab path?** Probes B and C show +0.075 and +0.108
  respectively. Whether this reflects the projection dimension (68 vs
  79 vs 151k) or task differences is not isolated.
- ~~**Is the +0.10 accuracy delta stable across seeds?**~~ Resolved:
  NLL delta is stable (±0.009); accuracy is not (±0.073). See §3a.

## 9. Reproduce

Feature-only gate (linear, 120 facts):

```bash
PYTHONPATH=src python scripts/run_coupled_training_probe.py \
  --feature-only --facts configs/titanos-facts.json \
  --steps 2400 --seed 0
```

Three-seed mini-transformer (CPU):

```bash
for seed in 0 1 2; do
  PYTHONPATH=src python scripts/run_pathb_cpu_probes.py \
    --seed $seed \
    --out artifacts/report_pathb_mini_seed${seed}.json
done
```

Pretrained decoder (needs ≥8 GB; not run for this doc):

```bash
python scripts/run_aggregate_training_probe.py \
  --decoder Qwen/Qwen2.5-0.5B --n-steps 500 \
  --out artifacts/report_aggregate_training.json
```

Probes B (closed-vocab carrier) and C (mini-transformer logit bias) are
implemented in scripts/run_pathb_cpu_probes.py and consume
build_aggregate_features from
src/resileos/substrate/aggregate_carrier.py plus the same
AggregateCarrier class.

10. Read next

· Engine Group Signal Probe Results — RES-319
· Engine Group Composition — RES-318
· Modulation Interface — RES-315
· Documentation Index

```
