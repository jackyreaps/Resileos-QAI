---
doc: RES-602
title: Two-Head Integration Note
status: draft
depends_on: [RES-600, RES-601]
referenced_by: []
---

# Two-Head Integration Note

This document is an **implementation note**, not a specification. It records the
neural architecture that realises the objects of RES-600 and RES-601 in a
single model, with the corrections that were required for the code to match the
source mathematics.

## 1. The two heads

| Head | Source | Object |
|---|---|---|
| Geometric Manifold | RES-601 | `g_ij`, `V`, `Γ^k_ij`, `‖∇_X V‖²` |
| Variational Reduction | RES-600 | `Ψ_s`, `Π_o`, `Π_s`, `Γ_eff`, `δΨ̇_s` |

## 2. Head 2 — the corrected rate

The source specification (`Reduction_fep.md §3.1–3.2`) gives:

    Γ_eff = P_s · M_E · U''(Ψ_B)
    U''(Ψ_B) = f Ψ_B (Ψ_B − Ψ_A)

Substituting Axiom C (`M_E = G Ψ_B / (Ψ_B − Ψ_A)`):

    Γ_eff = P_s · G · f · Ψ_B²

Matching to the linearized FEP recognition rate `Γ(Π_o + Π_s)` requires
`Γ = G`, per RES-600 §4. With that assignment:

    Γ · (Π_o + Π_s) = G · f Ψ_B²

and the identity closes.

Three corrections relative to earlier drafts:

1. ** Γ = G, not Π_s · G. An earlier draft used Γ = Π_s · G for the FEP recognition rate, which does not close the identity. The source document Reduction_fep.md §3.1 writes Γ = Π_s · G, but this is a transcription error: the rate identity requires Γ = G (RES-600 §4.1, resolved). The code in reduction.py implements Γ = G.
2. **`f` is a free parameter**, not `Re_ε · 0.1`.
3. **`P_s` is the orthogonal projector onto `ker(L_H)`**, not a learned scalar
   map. If a learned projection is used as a stand-in, the docstring must say
   so.

## 3. Head 1 — the metric

The source specification marks the metric bridge **"To Be Supplied"**
(`Non_dual_adaptation.md §7`). The three open items are:

- Explicit identification of the coordinates.
- Derivation of `Re_ε` and `G` from the rheology layer.
- Positive-definiteness verification.

A neural implementation that uses a different metric (e.g. `g = LLᵀ + εI` with
`L = xW_L`) is **not** the bridge. It is a substitute. The docstring must say
which it is.

## 4. Orthogonality

The two heads are **not** two halves of one system. RES-601 is orthogonal to
RES-600. A model may compute both, but the FEP reduction does not require the
metric, and the parallel transport condition does not require the FEP rate.
This note describes an implementation that happens to compute both; it does not
claim that the source documents require a joint architecture.

## 5. What is not claimed

- That the two-head architecture is required by the source documents.
- That Head 1 recovers the QD-TER metric without the missing derivations.
- That Head 2's fit is a verification of the local reduction theorem. A real
  verification restricts to `|δΨ_s| < ε`, sweeps `ε`, and checks that the
  residual scales as `C_1 / λ_2`.

## 6. Numerical verification harness

`VerifiableFEPReductionHead.sweep_epsilon()` runs the reduction ODE across
a user-supplied set of perturbation scales. It returns:

- `epsilons`: the scales tested
- `errors`: the ODE fit MSE at each scale
- `slope`: log-log slope of `errors` vs `epsilons`
- `r_squared`: fit quality

The slope is the numerical estimate of the residual scaling exponent.
Under RES-600 §4 the residual is bounded by `C_1/λ_2`; the fitted slope
is the empirical exponent of that bound on the given trajectory.

A structured trajectory generator (`simulate_linear_ode`) is provided for
the test suite. It produces a `[1, T, D]` trajectory whose first component
follows `δΨ̇ = −γ · δΨ` exactly, embedded in a D-dimensional ambient space.
This lets tests verify that the reduction head recovers a **known** rate,
rather than fitting noise.
