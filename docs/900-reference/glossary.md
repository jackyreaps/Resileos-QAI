---
doc: RES-900
title: Glossary
status: stable
depends_on: []
referenced_by: [RES-000]
---

# Glossary

## Architecture

**Layer A — Classical Residual Core**
Deterministic, volume-preserving engine. Sole producer of the control packet.

**Layer B — HDRIFT Generative Substrate**
Consumes the control packet. Produces holographic drift, moment hypervectors,
and measured generative behavior. Never writes back into Layer A.

**Layer C — Quantum / Coherence Backend**
Speculative. Receives the identical control packet after measured validation
of the hybrid.

## Core terms

**Control Packet**
Fixed-size, typed, canonicalized artifact emitted once per step by the
classical core. See RES-201.

**Residual Membrane** (`M`)
Difference `W − W̃` between the target and its residual-compensation
reconstruction.

**Dynamical Scar** (`Λ`)
State variable updated per step. Retains memory of residual structure.

**Sharpness Monitor** (`ΔS`)
Scalar monitor of generative sharpness. Fed into the abstention machine.

**Residual-Flux Parity** (`μ`)
Binary state ∈ `{0, 1}` set by signed residual flux `F_res` with hysteresis.
Drives repulsion and cleanup routing.

**Continuous Residual Flux** (`F_res`)
Signed scalar from which `μ` is derived. Logged every step.

**Volume Preservation**
Per-step invariant `|log10(|det J|)| < 1e-9`. Owned by the classical core.

**Prime Tower**
Even/odd discrete schedule controlling residual rank. `rank =
PrimeTower(schedule_index)`.

**Residual Quanta** (`ε`)
The grid quantum `ε = 1/64`. Residual scales are integer multiples.

**Exponent** (`k`)
Integer exponent ∈ `[-16, +16]`. Scale value is `k · ε`.

## Substrate terms

**Moment Hypervector** (`μ_hv`, `ν_hv`)
Two hypervectors built from the control packet. `μ_hv` and `ν_hv` must be
non-collinear: `0.1 < cos(μ_hv, ν_hv) < 0.5`.

**Moment Bundle**
The frozen construction of `μ_hv` and `ν_hv` from separate moments
(`M_U`, `M_V`, `M_scale`, `M_scar`, `M_mon`). See RES-301.

**Holographic Drift**
    V(x) = <enc(x), ν_hv> / <enc(x), μ_hv> - x
Modulated by scar energy and parity.

**FPE**
Fractional Power Encoding. Real engine lives in leCore; a reference shim is
permitted but must preserve signature and invariants.

**VSA**
Vector Symbolic Architecture. Bind, bundle, cleanup operations.

**Abstention**
Output of the state machine: `CONTINUE | REPULSE | CLEANUP | ABSTAIN`.
See RES-302.

**Sigma-1 Gate**
Deterministic regime switch. Priority order:
`CLEANUP > REEMBED > REPULSE_ABSTAIN`. See RES-303.

## Operations terms

**Run Config**
Operational envelope declared before execution. See RES-400.

**X, Y**
Declared acceptance thresholds: NRMSE reduction % and horizon extension
steps. A run without declared X, Y is non-conformant.

**Five-Tuple**
Per-step log record:
`(reconstruction_rel_error, scar_energy, ΔS, μ, |log10|det J||)`.

## Read next

- [Documentation Index](../README.md) — RES-000
- [Overview](../100-foundations/overview.md) — RES-100
