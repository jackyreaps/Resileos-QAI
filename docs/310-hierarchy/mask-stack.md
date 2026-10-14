doc: RES-312
title: Layered Mask Stack
status: draft
depends_on: RES-306, RES-310
referenced_by: RES-313, RES-315

# Layered Mask Stack

A mask is a binary selection over optional feature bits. At small scale, masks
partition a landscape into basins. At large scale, with layered masks, the
partition boundary saturates: the boundary ceases to be a curve and becomes a
membrane. The regime change is the mask-to-sheath transition.

This document defines the mask stack as a constructive structure — something
the build produces, not something a diagnostic observes. It defines the layers,
the transition criterion, and the API. It does not define the basin metrics
used to observe the transition. Those are RES-304.

## 1. What a mask is

A mask is a `k`-bit selection over a fixed feature set. For the substrate, the
feature set is the oscillator band set from RES-306:

| Bit | Feature | Meaning when set |
|-----|---------|------------------|
| 0 | `csi` | Include causal-sandbox index in the packet |
| 1 | `order_parameter` | Include oscillator order parameter |
| 2 | `direction` | Include directional trend |
| 3..k-1 | reserved | Future features |

A mask is `tuple[bool]` of length `k`. The full stack is a sequence of masks,
ordered by depth. Layer 0 is the finest mask (most bits set); layer `K-1` is
the coarsest.

## 2. Why layers

At small `n`, a single mask is sufficient: the constraint boundary is a curve,
and a binary partition of feature space captures it. At large `n`, a single
mask is insufficient because the boundary's dimension grows with `n`. A stack
of masks, each coarser than the last, provides a multi-resolution partition:
the finest layer resolves local structure, the coarsest layer resolves global
structure.

The stack is the layered-mask answer to the size problem. The sheath is what
happens when the coarsest layer's boundary saturates and the multi-resolution
structure collapses into a single membrane.

## 3. Layer definition

A layer `l` is:

    Layer = {
        mask: tuple[bool],          # length k
        carriers: complex128[d],    # band carriers u_k from RES-306
        weight: float,              # contribution to the stack bundle
    }

`carriers` is the set of band carriers for the bits set in `mask`. `weight` is
the layer's contribution to the stacked hypervector. The default weight is
`1.0 / (l + 1)`, so finer layers dominate and coarser layers provide context.

The stack bundle is:

    stack_hv = normalize(sum_l weight_l * bind(stream_hv, carriers_l))

where `bind` is the codex's exact bind from RES-306.

## 4. Transition criterion

The mask-to-sheath transition is detected by RES-304's `sheath_metrics`. The
operational criterion is:

    is_sheath = (boundary_codim < codim_max) AND (depth < depth_min)

When `is_sheath` first becomes true, the stack has entered the sheath regime.
At that point, the coarsest layer's boundary fills the state space and the
multi-resolution structure provides no further discrimination.

The stack API exposes this as:

    is_saturated() -> bool

which returns `True` when the current stack configuration is in the sheath
regime.

## 5. Construction API

    stack = MaskStack(dim=512, k=4, n_layers=3, seed=0)
    stack.add_layer(mask=(True, True, True, False))
    stack.add_layer(mask=(True, True, False, False))
    stack.add_layer(mask=(True, False, False, False))
    hv = stack.encode(stream_hv)

`add_layer` validates that the mask is a valid `k`-tuple and that the layer's
carriers are near-orthogonal to existing layers' carriers. If two layers have
identical masks, `add_layer` raises.

`encode` returns the stack bundle. It is a pure function of `stream_hv` and the
stack configuration.

## 6. Non-claims

- No compression claim. The stack is a re-encoding. It does not reduce
  information content.
- No semantic claim. "Layer 0" and "layer K-1" are depth-ordered, not
  semantically ordered.
- No learned structure. Masks are supplied by the caller. The stack does not
  search for optimal masks.
- No capacity guarantee. The stack's capacity is RES-313's problem.
- No claim that the sheath is a failure. The sheath is a regime. Whether it is
  desirable depends on the application. RES-315 is where that is decided.

## 7. Open questions

- **Optimal layer count.** Given `n` and `dim`, how many layers should the stack
  have before the coarsest layer saturates? This is a RES-313 input.
- **Layer weight schedule.** Is `1 / (l + 1)` the right schedule, or should
  weights follow the capacity of each layer's mask?
- **Carrier orthogonality.** Band carriers from RES-306 are near-orthogonal by
  construction. Does stacking layers with overlapping masks violate this? The
  `add_layer` validation checks exact overlap but not near-overlap.
- **Sheath as feature.** If the sheath regime is reachable, is it a failure mode
  or a feature? A membrane boundary might be useful for some modulation
  consumers. This is RES-315's decision.
