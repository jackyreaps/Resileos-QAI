---
doc: RES-101
title: Architecture
status: stable
depends_on: [RES-100]
referenced_by: [RES-102, RES-200, RES-300]
---

# Architecture

## Layer stack

| Layer | Components | Status |
|---|---|---|
| A. Classical Residual Core | Residual sub-bit compression; unipotent Jacobian; residual membrane M; dynamical scar Λ; `exp(ad_Λ)`; sharpness ΔS; residual-flux parity μ; volume-preservation guards; Prime Tower schedule | stable |
| Control Packet | The single interface between layers | stable |
| B. HDRIFT Adapter | Packet → moment hypervectors (μ_hv, ν_hv); scar- and parity-modulated holographic drift field; thin bridge to the leCore VSA substrate | stable |
| B. HDRIFT Substrate | VSA bind / bundle / cleanup; measured abstention with provenance; HRNN measure-first evaluation | stable |
| C. Quantum / Coherence Backend | Residual ledger or coherence-engine hand-off of the control packet | speculative |

## Abstraction boundaries

1. The classical core is the **sole producer** of the control packet.
2. The HDRIFT substrate **never writes back** into the classical core.
3. The quantum backend receives the **identical** packet, after measured
   validation of the hybrid.

## The control packet

Fixed-size, typed, canonicalized. See RES-201 for the field schema and
RES-202 for the hash rules.

## Where the invariants live

| Invariant | Owner |
|---|---|
| Volume preservation (`|log10|det J|| < 1e-9`) | Classical core |
| Residual-flux parity hysteresis | Classical core |
| Scar dynamics | Classical core |
| Moment-bundle collinearity band | Substrate |
| Abstention state machine | Substrate |
| Sigma-1 gate priority | Substrate |

## Read next

- [Design Principles](design-principles.md) — RES-102
- [Classical Core](../200-core/classical-core.md) — RES-200