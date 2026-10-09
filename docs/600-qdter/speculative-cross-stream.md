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

| Item | Status |
|---|---|
| Drafter checkpoint for Muse Glimmer 30B | External (llama.cpp PR #26841) |
| Trained `LowRankMetricHead` on real trajectories | Not started |
| `sweep_epsilon` run on a real FEP trajectory | Pending |
| Integration test of the full speculative pass | Not started |
| Zero-overhead overlap scheduler | Not started |

## 7. Where this fits in the doc set

RES-603 is a runtime integration note. It depends on RES-600 and RES-601
because it may invoke their heads. It does not extend them.
