---
doc: RES-100
title: Overview
status: stable
depends_on: []
referenced_by: [RES-101]
---

# Overview

Resileos-QAI is a layered architecture for extreme-compression residual
learning with a generative hypervector substrate.

## The stack

    Classical Residual Core  →  Control Packet  →  HDRIFT Generative Substrate
                                                     ↓ (optional, gated)
                                              Quantum / Coherence Backend

## What each layer owns

- **Classical Residual Core** — volume preservation, dynamical scar memory,
  residual-flux parity, hierarchical unipotent structure, residual quanta,
  sub-bit compression. Emits one control packet per step.
- **HDRIFT Generative Substrate** — holographic drift, moment hypervectors,
  measured generative behavior. Consumes the packet. Never writes back.
- **Quantum / Coherence Backend** — speculative. Receives the same packet,
  only after the classical loop is trained and measured.

## Why it is layered

Each layer has a single, well-defined contract. The classical core is
deterministic and measurable. The substrate is generative and measurable.
The backend is downstream and gated. No abstraction level is mixed inside a
single loop.

## What it is not

- Not a claim of quantum speed-up.
- Not a claim of biological fidelity.
- Not a trained system out of the box. The front-end requires training.

## Read next

- [Architecture](architecture.md) — RES-101
- [Design Principles](design-principles.md) — RES-102