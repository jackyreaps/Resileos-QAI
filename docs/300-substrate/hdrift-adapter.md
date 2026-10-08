---
doc: RES-300
title: HDRIFT Adapter
status: stable
depends_on: [RES-201, RES-202]
referenced_by: [RES-301, RES-302, RES-303, RES-402]
---

# HDRIFT Adapter

The adapter is the thin bridge between the classical core and the HDRIFT
substrate. It consumes the frozen control packet (RES-201) read-only and
produces moment hypervectors and a holographic drift field.

## Responsibilities

1. Encode the control packet into moment hypervectors `(μ_hv, ν_hv)`
   per the moment-bundle contract (RES-301).
2. Construct a holographic drift field modulated by scar energy and
   residual-flux parity:

        V(x) = <enc(x), ν_hv> / <enc(x), μ_hv> - x

   Step shrinks by scar energy; extra repulsion applied when `μ = 1`.
3. Route `ΔS` and `μ` into the abstention state machine (RES-302).
4. Hand drift and moments to the leCore VSA substrate for bind / bundle /
   cleanup and measured abstention.

## Contract with the classical core

- The adapter **never writes back** into the classical core.
- The adapter never modifies the packet.
- The adapter is a pure function of `(packet, x_enc)` given fixed seeds.

## Contract with the substrate

- The adapter emits `(μ_hv, ν_hv, drift, ratio)`.
- Hypervector dimension and seeds are fixed in the run config (RES-400).
- Bind, bundle, and cleanup are substrate operations; the adapter does not
  implement them directly.

## leCore boundary

`fpe_encode` is a reference shim. The real leCore Fractional Power Encoding
engine must preserve:

- unit-norm output
- determinism in `(x, dim, seed)`
- signature `encode(x, dim, seed) -> np.ndarray`

Internal scheme may differ.

## Acceptance (owned by RES-301)

- `0.1 < cos(μ_hv, ν_hv) < 0.5`
- Drift-ratio variance above the declared floor
- Drift-ratio SNR logged

The adapter references these; it does not restate them.

## Read next

- [Moment Bundle](moment-bundle.md) — RES-301
- [Abstention](abstention.md) — RES-302
- [Sigma Gate](sigma-gate.md) — RES-303