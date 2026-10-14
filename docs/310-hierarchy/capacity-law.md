---
doc: RES-313
title: Composition Capacity Law
status: draft
depends_on: RES-310, RES-311, RES-312
referenced_by: RES-314, RES-315
---

# Composition Capacity Law

RES-310 gives a per-bundle capacity: `C(dim) = floor(dim / (2 ln dim))`. That
bound is local. It says how many items one bundle can hold before crosstalk
exceeds cleanup SNR. It says nothing about how capacity behaves when bundles are
nested to depth `K`, when a streaming state accumulates packets, or when a mask
stack re-bundles the state.

This document states the composition law: how capacity scales with depth, stream
length, and stack height. It is a bound, not a guarantee. It is stated as a
conjecture with the experiment that would falsify it.

## 1. Per-bundle capacity (restated)

From RES-310 §1:

    C(dim) = floor(dim / (2 * ln(dim)))

| dim | C(dim) |
|-----|--------|
| 256 | 23 |
| 512 | 41 |
| 1024 | 74 |
| 2048 | 134 |
| 4096 | 244 |

This is the number of items a single bundle can hold before the similarity
between a stored item and its noised recall falls below the cleanup threshold.
It is derived from the random-phase model in RES-306 §6: `E|noise|^2 = n / D`
for `n` stored items in `D` components. Setting signal-to-noise to 1 and solving
for `n` gives the formula above with the `2 ln dim` factor from the SNR
threshold.

## 2. Depth accumulation

A level-`L` packet contains tokens that have been re-bundled `L` times. Each
re-bundling adds crosstalk. The depth-`L` crosstalk is not `L * (n / D)` — it is
worse, because each level's bundle contains the crosstalk of its children.

Under the random-phase model, the depth-`L` noise variance is:

    E|noise_L|^2 = (n_0 / D) * sum_{l=0}^{L-1} (n_l / D)^l

where `n_l` is the number of items bundled at level `l`. This is a geometric
sum. For `n_l / D < 1` (which is the operating regime), the sum converges:

    E|noise_inf|^2 = (n_0 / D) / (1 - n_max / D)

where `n_max` is the maximum bundle size across levels. The depth-`L` capacity
is therefore:

    C_depth(dim, L) = C(dim) * (1 - n_max / D)

for large `L`. The factor `(1 - n_max / D)` is the depth penalty. At
`n_max / D = 0.5`, capacity halves. At `n_max / D = 0.9`, capacity is one tenth.

## 3. Stream capacity

The streaming state (RES-311) accumulates packets into a single hypervector. Its
capacity is `C(dim)` — the flat-bundle bound. At `decay = 1`, every packet ever
emitted contributes, so the state's effective `n` grows without bound and
crosstalk grows without bound. At `decay < 1`, the effective `n` saturates at
`1 / (1 - decay)` packets.

The stream capacity law is:

    C_stream(dim, decay) = min(C(dim), 1 / (1 - decay))

The `min` is the binding constraint. For `decay = 1`, capacity is `C(dim)` and
the state is a lossy summary of the entire stream. For `decay = 0.99`, capacity
is 100 packets, and the state is a rolling window.

## 4. Stack capacity

The mask stack (RES-312) re-bundles the stream hypervector into `L` layers.
Each layer adds crosstalk. The stack capacity is:

    C_stack(dim, L) = C(dim) / L

The factor `1 / L` is the stack penalty. At `L = 3` layers, capacity is one
third. This assumes each layer's bundle is independent; if layers share
carriers, the penalty is worse.

## 5. The composition law

Combining §2, §3, and §4:

    C_total(dim, L_depth, decay, L_stack)
        = min(C(dim), 1 / (1 - decay))
        * (1 - n_max / D)
        / L_stack

This is the number of distinguishable items the composed system can carry. It
is a product of three penalties:

| Factor | Penalty | Source |
|--------|---------|--------|
| `(1 - n_max / D)` | Depth | Re-bundling at each level |
| `1 / L_stack` | Stack | Layer re-bundling |
| `min(..., 1 / (1 - decay))` | Stream | Running state accumulation |

## 6. The trillion-token check

At trillion tokens with `c_0 = 32` tokens per window:

    windows = 1e12 / 32 = 3.125e10

If the stream state holds every window (`decay = 1`), and `dim = 4096`
(`C = 244`):

    C_stream = 244

So the state can distinguish 244 windows. Everything else is crosstalk. To
distinguish all 3.125e10 windows, you need either:

- `decay` small enough that `1 / (1 - decay) >= 3.125e10`, which requires
  `decay >= 1 - 3.2e-11`. At that decay, the state is essentially non-decaying
  and capacity is still 244.
- A hierarchy deep enough that windows are stored at different levels, not
  accumulated into a single state. This is RES-310's tree, and the depth
  penalty `(1 - n_max / D)` applies.

The trillion-token reach question is therefore: **is there a
`(dim, capacities, decay, stack)` configuration where `C_total >= 3.125e10`?**
Under the composition law above, the answer is no — `C_total` is bounded by
`C(dim)`, which is at most a few hundred. The law says the composed system
cannot carry trillion distinguishable items in a single hypervector, at any
depth.

This is a negative result. It does not mean trillion-token modulation is
impossible. It means the modulation cannot be a lookup over stored items. It
must be something else — a projection, a sketch, a gradient. RES-315 defines
what.

## 7. Non-claims

- No learned capacity. The law assumes random-phase keys and no training. A
  trained projection could exceed it.
- No claim about the bound's tightness. The geometric-sum derivation is an
  approximation. The exact crosstalk at finite depth is measured, not derived.
- No claim that `C_total` is achievable. It is an upper bound.
- No claim about downstream utility. A system with `C_total = 244` may still
  modulate a downstream model usefully. Capacity is not utility.

## 8. Open questions

- **Falsification.** The law predicts `C_depth(dim, L) = C(dim) * (1 - n_max /
  D)`. Measure descent accuracy at each depth `L` and fit against this
  prediction. If the fit fails, the geometric-sum model is wrong.
- **Trained capacity.** If the codex is trained rather than random, does
  capacity exceed `C(dim)`? This is not in scope for the current build.
- **The trillion-token question.** If `C_total` is bounded, what *is* the
  modulation? This is RES-315's central problem.
