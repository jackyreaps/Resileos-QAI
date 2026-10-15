doc: RES-606
title: Metric Bridge Candidate Derivations
status: candidate
depends_on: [RES-600, RES-601, RES-602]
referenced_by: [RES-604]

# Metric Bridge Candidate Derivations

Candidate closed forms for the four open items of RES-601 §7. The
structure is fixed. The constants are tunable parameters, not derived
quantities. Any value here is either a monitor already produced by
`core.monitors()` or an explicit tuning parameter marked `[proposal]`.

This is not a completed source derivation. It gives the four items a
concrete algebraic form so a candidate metric can be instantiated,
tested for positive-definiteness, and compared against the residual
substrate's own state. It does **not** unlock `BridgeMetricHead`.

## 0. Status

The canonical bridge (`BridgeMetricHead` in
`src/resileos/substrate/geometry.py`) remains locked. Its four open
items are:

1. Coordinate map `x`.
2. `Re_ε(x)` field.
3. `G(x)` field.
4. `M_E` shape.

Per RES-604, items 1–3 require source material from the physics layer.
This document records candidates built only from in-repo quantities.
They are labelled `candidate` throughout.

## 1. Coordinate map x

**Candidate.**

    x = (j, r, s, n)

| Component | Meaning | In-repo source |
|---|---|---|
| `j` | discrete index along the residual hierarchy | `schedule_index` |
| `r` | ratio of two internal accounting terms | placeholder; no runtime monitor yet `[proposal]` |
| `s` | net scalar residual at the address | `F_res` |
| `n` | stacking depth of the residual packet | `rank` |

**Software reduction.** For code, project to a scalar slow coordinate:

    x_slow = j / max(schedule_index_range, 1)

matching the FEP head's 1-D slow coordinate in
`VerifiableFEPReductionHead`. The full vector chart is not wired.

**Open.** The `r` component has no monitor in the current packet. It is
recorded as a placeholder.

## 2. Residual Reynolds field Re(x)

    ε = 1/64                       (repo constant, RES-200)
    p = 4                          [proposal]
    L = ε^(1/p)                    ≈ 0.3536
    τ = 1/512                      [proposal; see note]
    k = 1/64                       [proposal]
    v = k · L² / τ

**Local rate scale.** Identify the discrete velocity with the residual
flux magnitude the packet already emits:

    |u|(x) = |F_res|(x)

Then:

    Re(x) = |u|(x) · L / v
          = |F_res|(x) · τ / (k · L)

**Coefficient at defaults.** `τ / (k · L) ≈ 0.354`, which places
`Re ≈ 0.35 · |F_res|` — O(1) relative to the monitor range, which is
the regime where the conformal factor matters.

**Note on τ.** `τ = 1/3584 = 2^(-9) · 7^(-1)` is an odd constant with
no derivation. `1/512` and `1/4096` are cleaner and put the coefficient
in the same O(1) regime. `1/512` is used as the default here; `1/3584`
is recorded as an alternative for continuity with earlier drafts.

**Tuning table.**

| `p` | `τ` | `k` | coefficient |
|---|---|---|---|
| 4 | 1/512 | 1/64 | ≈ 0.354 |
| 4 | 1/3584 | 1/64 | ≈ 0.0505 |
| 4 | 1/64 | 1/64 | ≈ 2.83 |
| 2 | 1/512 | 1/64 | ≈ 1.000 |
| 8 | 1/512 | 1/64 | ≈ 0.210 |

**Positivity.** `Re ≥ 0` for any positive parameters. `1/(1+Re)` is
positive definite for all finite `Re > −1` (see `substrate/spd.py`).

## 3. Coherence field G(x)

**Working definition** (matches `coherence_schedule` in
`substrate/reduction.py`):

    G(t) = g_0 · (1 + g_ramp · t/(T-1))

with default `g_0 = 0.85` and `g_ramp ≥ 0`. This is the only form used
by the current implementation.

**Alternate form** `[proposal]`, not wired:

    G(x) = g_0 · (1 + α · |ΔS|(x))^(-1)

`α` is not fixed. Recorded for future work only.

## 4. Endocrinal / residual matrix M

**Candidate shape: scalar times identity (conformal).** This records
the scalar-vs-matrix ambiguity without resolving it by fiat: RES-600
treats `M_E` as a scalar; RES-601 §7 writes `M_E^(ij)`.

    M^(ij) = m_0 · δ^ij
    m_0 = φ_B / (φ_B − φ_A)

Note: `m_0` does **not** include G. G appears separately in §5. This
avoids the double-count that a form like `m = G·φ_B/(φ_B − φ_A)` would
introduce when substituted into the §5 expression.

**Matrix upgrade** `[proposal]`, deferred: a diagonal multi-channel
form

    M = m_0 · diag(w_1, …, w_k, 1, …, 1)

with channel weights not yet specified in this repository. Until
measured weights exist, keep the scalar form.

## 5. Assembled candidate metric

Full form (RES-601 §7):

    g_ij(x) = δ_ij · 1/(1+Re(x)) + (G(x)/(φ_B − φ_A)) · M^(ij)

Under the scalar `M` candidate:

    g_ij(x) = δ_ij · [ 1/(1+Re(x)) + G(x)·m_0/(φ_B − φ_A) ]

At the FEP-head defaults `φ_A = 0.5`, `φ_B = 1.5`, `m_0 = 1.5`,
`φ_B − φ_A = 1.0`:

    c(x) = 1/(1+Re(x)) + 1.5 · G(x)

and `g_ij = c(x) · δ_ij`.

**This is a conformal metric.** Both terms are proportional to `δ_ij`.
The metric has no directional content in the scalar-`M` regime. Its
sole effect is a scalar rescaling of the identity. The conformal case
is specified as a candidate; the directional (matrix) case is deferred.

**SPD check.** Both terms are positive for `Re ≥ 0`, `G > 0`, `m_0 > 0`.
Run `assert_spd` from `substrate/spd.py` on any numerical realization.

## 6. Status

| Item | Candidate status |
|---|---|
| Coordinates `x` | Defined as a vector; scalar reduction for code. `r` component has no monitor yet. |
| `Re(x)` | Closed form from `ε`, `L`, `v`, `F_res`. Constants are `[proposal]`. |
| `G(x)` | Schedule form primary. Residual-monitor form recorded, unwired. |
| `M` shape | Scalar × I candidate, no G. Multi-channel diag deferred. |
| SPD | Utility landed. Conformal candidate is SPD by algebra. |
| Cheeger / Tikhonov / cubic | **Open** — separate analysis required. |
| Neighborhood size | **Open** — ε-ball estimate required. |

Items 1–4 are candidate-closed in this document. The two analysis rows
and neighborhood size remain open.

## 7. What this does not claim

- That the four candidates are the canonical forms of RES-601 §7.
- That the constants `p`, `τ`, `k`, `α` are derived from any source.
- That the metric has directional content in the scalar-`M` regime.
- That `BridgeMetricHead` can be unlocked with these forms. It cannot;
  source derivations for items 1–3 are still missing.
- That this document replaces RES-601 §7. It supplies a candidate path
  so the conformal case can be tested for positive-definiteness against
  real monitors.

## 8. What is used from the repo

- `F_res`, `ΔS`, `μ`, `Λ`, `rank`, `schedule_index` — from
  `core.monitors()` and the control packet (RES-201).
- `ε = 1/64` — RES-200 residual grid.
- `φ_B − φ_A = 1.0` — defaults of `VerifiableFEPReductionHead`.
- `coherence_schedule` — `substrate/reduction.py`.
- `assert_spd` — `substrate/spd.py`.

No QD-TER object is imported. No new constant is introduced without a
`[proposal]` marker.

## 9. Read next

- [FEP Reduction Bridge](fep-reduction.md) — RES-600
- [Non-Dual Adaptation Layer](non-dual-adaptation.md) — RES-601 §7
- [Two-Head Integration Note](integration.md) — RES-602
- [QD-TER Bridge Status](status.md) — RES-604
