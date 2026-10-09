---
doc: RES-601
title: Non-Dual Adaptation Layer
status: conjectural
depends_on: []
referenced_by: [RES-602]
related_to: [RES-600]
---

# Non-Dual Adaptation Layer

Status: **conjectural**. Conditional on the physics suite supplying a
Riemannian metric on the human-medium parameter space.

Source: `QD-TER-Human-Medium/QD-TER_HumanMedium_v9.0/Theory/Non_dual_adaptation.md`.

Status vocabulary: `conjectural` means "formal structure awaiting physical
input". See RES-000 for the extended status enum.

## 1. Scope

This layer formalizes world-model updates as covariant derivatives on a
Riemannian manifold. Without the metric from the physics suite, the layer is a
formal structure without content.

**Orthogonality.** This layer is **orthogonal** to the FEP reduction of RES-600.
It is not a consequence of that reduction, and the FEP reduction does not depend
on it. The two are separate specifications. This is why `depends_on` is empty
above; the relation is captured by `related_to`.

## 2. Axioms

**Axiom M (metric).** The parameter space carries a Riemannian metric `g_ij(x)`
derived from QD-TER quantities (cognitive glue, `Re_ε`, endocrinal matrix norm).

**Axiom V (intentionality vector).** There exists a vector field `V` on this
manifold, transported along update trajectories.

**Axiom Ω (coherence scalar).** `Ω = g_ij V^i V^j`.

## 3. Parallel transport condition

    ∇_X V = 0

expands in components to:

    ∂V^k/∂x^i + Γ^k_ij V^j X^i = 0

with Christoffel symbols:

    Γ^k_ij = ½ g^{kl} (∂_i g_{jl} + ∂_j g_{il} − ∂_l g_{ij})

A flat metric gives `Γ = 0`, in which case the layer is trivial. The layer is
only nontrivial when `g_ij(x)` is derived from QD-TER quantities.

## 4. Holonomy

Under a closed loop `γ`, `V(after) = H_γ · V(before)` with `H_γ ∈ SO(d)`.

## 5. Violation detection

`‖∇_X V‖ ≠ 0` marks a trajectory that does not preserve the invariant direction.

## 6. What is not claimed

- That `V` is a fixed vector in `R^d`. It is a section of a vector bundle.
- That `Ω < 1` registers as a dielectric grid break.
- That the metric bridge below is derived from the physics suite.

## 7. Metric bridge (to be supplied)

    g_ij(x) = δ_ij · 1/(1 + Re_ε(x)) + (G(x)/(Ψ_B − Ψ_A)) · M_E^(ij)

Requires:

- Explicit identification of the coordinates `x`.
- Derivation of the `Re_ε` and `G` dependence from the rheology layer.
- Verification that the resulting metric is positive definite.

## 8. Status

Conjectural. See `CLAIMS.md §6` (C3, C4, C5) in the QD-TER suite.

## 9. Note on the Gnosis Frame

`Frame/Gnosis_frame.md` is **adjacent, not dependent**. The mathematics in this
document does not require the Frame. The Frame does not enter the parallel
transport condition, the metric bridge, or the holonomy.
