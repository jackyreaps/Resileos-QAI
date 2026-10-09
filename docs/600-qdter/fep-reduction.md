---
doc: RES-600
title: FEP Reduction Bridge
status: conditional
depends_on: [RES-200]
referenced_by: [RES-602]
related_to: [RES-601]
---

# FEP Reduction Bridge

This document records the QD-TER FEP reduction as it applies to the Resileos
classical core. It is a **local, conditional** specification. It is not a global
claim, and it does not reopen RES-200 through RES-402.

Source: `QD-TER-Human-Medium/QD-TER_HumanMedium_v9.0/Theory/Reduction_fep.md`.

Status vocabulary: `conditional` means "true under the stated assumptions
(Axioms G and C below)". See RES-000 for the extended status enum.

## 1. Scope

The reduction is local in state space and conditional on two extra modeling
assumptions (Axioms G and C below). Global fixed-point alignment and full
nonlinear identity are explicitly not claimed.

## 2. Axioms

**Axiom D (dynamics).**

    dΨ/dt = −L_H(t)Ψ + M_E(t)·F(Ψ, f)
    F(Ψ, f) = f · Ψ(Ψ_A − Ψ)(Ψ − Ψ_B)

**Axiom S (spectral structure).** `λ_2 ≫ λ_slow`.

**Axiom G (generative model — extra assumption).**

    q(s) = N(μ, Σ)
    μ = Ψ_s
    Π_o = f Ψ_A Ψ_B
    Π_s = f Ψ_B (Ψ_B − Ψ_A)

**Axiom C (endocrinal consistency — extra assumption).**

    M_E = G · Ψ_B / (Ψ_B − Ψ_A)
    G = √(OXTR · GJ)

## 3. The local reduction

Let `P_s` be the **orthogonal projector onto `ker(L_H)`** and let
`Ψ_s = P_s Ψ`. Let `δΨ_s = Ψ_s − Ψ_B`. For perturbations small enough that the
cubic remainder is negligible, the projected dynamics linearize to:

    δΨ̇_s = −Γ_eff · δΨ_s + O(ε)

with

    Γ_eff = P_s · M_E · U''(Ψ_B)
    U''(Ψ_B) = f Ψ_B (Ψ_B − Ψ_A)

Substituting Axiom C:

    M_E · U''(Ψ_B)
        = [G Ψ_B / (Ψ_B − Ψ_A)] · [f Ψ_B (Ψ_B − Ψ_A)]
        = G · f · Ψ_B²

so that

    Γ_eff = P_s · G · f · Ψ_B²

## 4. Matching to the linearized FEP recognition dynamics

The linearized Laplace FEP recognition dynamics are:

    δμ̇ = −Γ(Π_o + Π_s) δμ + O(ε)

Under `μ = Ψ_s`, matching the two rates requires

    P_s · G · f · Ψ_B²  =  Γ · (Π_o + Π_s)

Expanding the right-hand side:

    Π_o + Π_s = f Ψ_B · [Ψ_A + (Ψ_B − Ψ_A)]
              = f Ψ_B²

Therefore the identity closes **iff `Γ = G`**:

    Γ · (Π_o + Π_s) = G · f Ψ_B²

and the projected rate is

    Γ_eff = P_s · Γ · (Π_o + Π_s)

with `Γ = G`.

### 4.1 Open item — Γ definition

The source document `Reduction_fep.md §3.1` writes **`Γ = Π_s · G`** rather
than `Γ = G`. Under `Γ = Π_s · G`:

    Γ(Π_o + Π_s) = Π_s · G · (Π_o + Π_s)
                 = f Ψ_B (Ψ_B − Ψ_A) · G · f Ψ_B²
                 = f² · G · Ψ_B³ (Ψ_B − Ψ_A)

This does **not** equal `P_s · G · f · Ψ_B²`. The two expressions differ by a
factor `f Ψ_B (Ψ_B − Ψ_A)`.

Two possibilities:

1. **Transcription.** The source may define `Γ_o = G` for the object that
   appears in the FEP recognition rate, and `Γ = Π_s · G` for a different
   quantity that does not appear in this identity.
2. **Source inconsistency.** The source may intend `Γ = G` and the published
   expression `Γ = Π_s · G` may be a typographical error.

Until resolved, this document uses `Γ = G` for the rate identity and records
the discrepancy here as an open item. RES-602 §2 depends on this resolution.

## 5. Boundary of the claim

Established:

- The linearized projected QD-TER dynamics equals the linearized FEP
  recognition dynamics in a neighborhood of `Ψ_B`, under `Γ = G`.
- The consistency condition `M_E = G Ψ_B / (Ψ_B − Ψ_A)` is derived from the
  requirement that the linearized rates match.
- `Π_o` and `Π_s` are derived as curvatures of `U` at the two wells.

Not claimed:

- Global fixed-point alignment.
- Full nonlinear identity.
- Unconditional recovery from the published suite.
- That `Γ = Π_s · G` holds in the rate identity (see §4.1).

Residual bound: `‖error‖ ≤ C_1 / λ_2`.

## 6. Open items

| Item | Status |
|---|---|
| Γ definition (§4.1) | Discrepancy between source and derivation |
| Cheeger bound for the specific hypergraph | Sketch only |
| Tikhonov constants `C_1`, `C_2` | Symbolic |
| Linear neighborhood size | Not bounded |
| Cubic residual bound away from `Ψ_B` | Not bounded |
| Numerical verification inside the local regime | Planned |

## 7. What this does not say

This document does not modify the classical core. The `f` parameter in Axiom D
is a **free scalar** in the QD-TER specification; it is **not** `Re_ε · c` for
any constant `c`. The slow projector `P_s` is a kernel projector, not a learned
scalar map. The FEP reduction does not depend on the metric of RES-601.
