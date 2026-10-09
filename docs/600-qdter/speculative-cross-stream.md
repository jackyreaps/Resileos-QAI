---
doc: RES-603
title: Speculative Cross-Stream Layer
status: draft
depends_on: [RES-600, RES-601, RES-602]
referenced_by: []
---

# Speculative Cross-Stream Layer

This document is an **implementation note**, not a specification. It records
the runtime layer that carries a speculative draft block through the Resileos
substrate heads in a single forward pass. It does not modify RES-600 or RES-601.

## 1. Scope

The layer sits between a target language model's hidden states and the Resileos
substrate heads. It performs three operations in order:

1. **Block diffusion.** A DFlash-style drafter emits a fixed-size block of
   speculative tokens in one forward pass.
2. **Contextual fusion.** Hidden states from several target-model layers are
   concatenated and projected to a single trunk state.
3. **Tree verification.** A causal tree-attention mask restricts each
   speculative position to its direct ancestors, so branches do not contaminate
   each other.

The substrate heads of RES-600 and RES-601, if invoked, operate on the trunk
state. They are optional; the layer runs without them.

## 2. Block size and layer set

| Parameter | Value | Source |
|---|---|---|
| DFlash block size | 16 tokens | DFlash (Chen, Liang, Liu; ICML 2026) |
| EAGLE-3 fusion layers | low / mid / high (3 layers) | EAGLE-3 (Li et al., 2024) |
| DFlash fusion layers (Muse Glimmer 30B) | (1, 13, 25, 37, 49) | DFlash config |

The block size is fixed at 16. The drafter is trained to predict the whole
block in one forward pass; attention inside the block is bidirectional, which
is the "diffusion" part.

## 3. Tree attention mask

The mask is the standard Medusa/EAGLE construction: for a tree with parent
array `parents[]`, position `i` attends to `j` iff `j` is an ancestor of `i`.
The mask is strictly causal; it is not a lower-triangular full mask. Using a
full triangular mask on a multi-branch tree lets distinct branches see each
other's tokens, which defeats the point of the tree.

## 4. Substrate heads (optional)

If `LowRankMetricHead` is invoked, it computes the covariant parallel transport
penalty `‖∇_X V‖²` on the trunk state. The docstring of that head labels it a
**structural proxy substitute** because it uses `g = L Lᵀ + εI` rather than the
RES-601 §7 metric bridge. See RES-602 §3.

If `VerifiableFEPReductionHead` is invoked, it projects the trunk state onto
`ker(L_H)`, evaluates the linearized ODE residual `δΨ̇_s = −Γ_eff · δΨ_s`, and
returns the fit error. The docstring of that head labels it the **canonical FEP
subspace verifier** because it implements the RES-600 §3 quantities.

## 5. What this layer is not

- It is not a claim that DFlash or EAGLE-3 are components of Resileos. They are
  external methods; this layer is an integration point.
- It is not a claim that the substrate heads are required for speculative
  decoding. They are optional diagnostics.
- It is not a security statement. The runtime layer does not touch LASLS or any
  cryptographic component.

## 6. Open items

| Item | Status | Notes |
|---|---|---|
| Muse Glimmer 30B drafter checkpoint | External | Not distributed with this repo |
| Trained `LowRankMetricHead` on real trajectories | Not started | Requires item below |
| Real-trajectory sweep | Pending — **data mode fixed** | See note |
| Full speculative integration test | Not started | Depends on drafter checkpoint |
| Overlap scheduler | Not started | Last in line |

### 6.1 Real-trajectory sweep — data mode

An earlier version of `scripts/run_fep_sweep.py --data` overwrote
coordinate 0 of the loaded trajectory with a synthetic offset
(`t[:, 0, 0] = 1.5 + eps`) before running the sweep. That is not a real
perturbation — it discards the trajectory's actual initial deviation and
substitutes a hardcoded one.

The current implementation is honest about what real data can support:

- **`[K, T, D]` with `K ≥ 3`** — real ε sweep. Ψ_B is estimated from the
  mean of the last 10% of each trajectory on coordinate 0. ε_k is the
  actual deviation `traj_k[0, 0] − Ψ_B`. The log-log fit is over the K
  trajectories' own ε values. This is a genuine sweep.
- **`[T, D]` or `K < 3`** — single-trajectory mode. The head reports the
  ODE residual at the actual ε and the slope field is `null`. A slope
  requires ≥3 trajectories with distinct initial deviations.

Note: the trajectory file does not carry a G(t) series. The sweep uses
`--g-field` as a constant. If the real data has time-varying G, that must
be supplied separately; the current interface does not accept it.

## 7. Where this fits in the doc set

RES-603 is a runtime integration note. It depends on RES-600 and RES-601
because it may invoke their heads. It does not extend them.
