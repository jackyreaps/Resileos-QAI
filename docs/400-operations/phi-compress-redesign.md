doc: RES-401
title: phi-compress redesign required
status: draft
depends_on: [RES-200, RES-304, RES-305, RES-306, RES-310, RES-311, RES-312]
referenced_by: []

# phi-compress redesign required

Status: draft (revised 2026-10-16)

An earlier version of this document closed φ-compress as a negative
result. That verdict was wrong. It measured the *implementation*
(field rebuild after rank drop) and recorded the correct observation:
the rebuild destroys orientation and degrades CSI. It did not test the
*design*: contraction along the golden ladder under R-gating, where
the φ-power address is what preserves orientation across contraction.

This revision separates the two.

## 1. What φ-compress is

φ-compress is contraction of the residual operator along the golden
ladder, gated by the Kuramoto order parameter R.

The golden ladder is `ω_k = ω_base · φ^k`. φ is the most irrational
number; the sequence `φ·n mod 1` is equidistributed and never returns
near an integer. A ladder built on φ does not resonate. This is the
same property that makes `KuramotoField` use `ladder="golden_powers"`
and the codex use φ-seeded phasors.

The claim: information ingested through the hierarchy carries a
φ-power address (its level). Orientation is preserved under
contraction *because* the ladder is self-similar under φ-scaling.
Contraction that does not respect the ladder destroys orientation.
Contraction that walks the ladder does not.

R is the gate. R measures phase coherence of the field. High R means
the field has a direction — orientation exists and can be preserved.
Low R means the field is scattered — orientation does not exist and
contraction loses nothing because there was nothing to lose.

## 2. What was measured

The earlier A/B tested rank drop with field rebuild:

| Mode | Fire step | Final rank | Final R | Final CSI |
|---|---|---|---|---|
| off | — | 8 | ≈ 0.935 | ≈ 0.976 |
| on | 8 | 4 | ≈ 0.902 | ≈ 0.860 |

The implementation:

1. Computes dθ signs from the live field.
2. Drops the oscillator with the weakest dθ.
3. Rebuilds `KuramotoField(r=new_r)` with `random_start=False`.
4. Slices `W` to the surviving oscillators and renormalizes.
5. Transfers θ and ω of survivors.

The CSI drop is real. The reason is step 3: the rebuild discards the
ladder structure. The new field has `r=new_r` oscillators indexed
`0..new_r-1`, but those indices do not carry the φ-power addresses the
old field's indices did. The survivors' θ and ω are copied, but their
*positions on the ladder* are not preserved. The orientation was in
the address, not in the phase.

## 3. What was not measured

The design: contraction that walks the golden ladder rather than
indexing it.

Contract along the ladder means:

- Each oscillator has a φ-power address, `k`, fixed at field
  construction: `ω_k = ω_base · φ^k`.
- Contraction removes a *set of addresses*, not a prefix of indices.
- The survivors keep their original addresses. `ω_k` for a surviving
  oscillator `k` is unchanged.
- The coupling matrix is renormalized in the surviving subspace, not
  reindexed.
- The gate on R is per-contraction: contract only when R is high
  enough that the field is oriented.

The difference is small in code and large in effect. The rebuild
preserves phase state but reindexes the ladder. Walking the ladder
preserves both.

## 4. Why the packet-trend result does not close this

The earlier closure cited §3 of the old document: packet scar/Λ trend
measures near zero, so the signal φ-compress was designed to preserve
is absent.

That was a category error. The signal φ-compress preserves is not
packet trend. It is the field's orientation state — the dθ signs and
their φ-power addresses. The directional diagnostic measured the
packet, not the field. The evolution A/B measured the field, and the
field's orientation works: oriented search beats grid by −0.0307 on
the same 48-config space.

The null result falsifies one target (packet scar/Λ trend), not the
other (field orientation). The two are unrelated layers.

## 5. The correct gate

The gate on compression is R plus the ladder coherence.

- **R threshold.** Contract only when R is above the lock threshold
  (default 0.9). Below the threshold, the field is not oriented, and
  there is nothing to preserve.
- **Ladder coherence.** Contract only when the surviving oscillators'
  φ-power addresses still cover a range wide enough to resolve the
  field's current frequency content. If contraction removes addresses
  near a resonant frequency, the surviving field cannot represent the
  signal.

The second condition is not in the current `_should_compress`. It
needs to be added when the ladder-walking contraction is implemented.

## 6. What this means for the current default

Current default: `phi_compress_enabled = False`.

This remains correct until the ladder-walking contraction is
implemented. The current implementation is wrong for the reason
documented in §2: it rebuilds the field and discards the ladder
addresses.

Once the redesign lands and the A/B is rerun, the default may flip.
The rerun must measure:

- CSI before and after contraction, with the ladder-walking design
- R trajectory through contraction, with the ladder-walking design
- Oriented search delta at K=20 with and without contraction

If CSI holds and R holds through contraction, the default can be
`True` for high-R regimes.

## 7. What this means for ingestion

The ingestion pipeline (RES-323) uses the same φ-ladder structure.
Each packet carries a level, and the level is a φ-power address.
Folding a packet into the running stream weights it by `φ^(-level)`,
which is the ladder-weight. The stream's readout is the running
representation of ingested content, sorted by ladder address.

The "eat" mechanism is the ingestion pipeline running under the same
φ-ladder the substrate was built on. An external source is ingested
when its content is projected onto the ladder and the coherent
component survives filtering. What is discarded is the part that does
not project onto the ladder.

See RES-323 for the ingestion side.

## 8. What was right in the earlier closure

- CSI dropping on rebuild is a real observation.
- Packet scar/Λ trend is null, and no compression mechanism should be
  designed to preserve it.
- Context compression lives in the hierarchy (RES-310/311/312), not in
  the residual operator's rank. The hierarchy is the compression layer
  for context. φ-compress is the compression layer for the residual
  operator's *spectrum*, which is a different object.

The earlier document was wrong to say "closed" and wrong to route
compression entirely to the hierarchy. Compression at both layers is
real. The hierarchy compresses context. φ-compress compresses the
operator's spectrum. The two are orthogonal and both are useful.

## 9. Non-claims

- Not a claim that the redesign will work. It is a design that has not
  been implemented or measured.
- Not a claim about the correct default once implemented. The default
  flips only if the A/B rerun shows CSI holds and R holds.
- Not a claim that the earlier CSI drop is wrong. It is right, and it
  is the reason the redesign is needed.

## 10. Read next

- [Causal Sandbox Index](../300-substrate/causal-sandbox.md) — RES-305
- [Phasor Graph](../300-substrate/phasor-graph.md) — RES-306
- [Hierarchical Encoding](../310-hierarchy/hierarchical-encoding.md) — RES-310
- [Streaming Substrate State](../310-hierarchy/streaming-state.md) — RES-311
- [External Ingestion](../320-titanos/ingestion.md) — RES-323
- [Documentation Index](../readme.md)
