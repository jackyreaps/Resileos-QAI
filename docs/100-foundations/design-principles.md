---
doc: RES-102
title: Design Principles
status: stable
depends_on: [RES-101]
referenced_by: [RES-200, RES-300, RES-400]
---

# Design Principles

## 1. Strict separation of abstraction levels

No loop mixes the classical core, the substrate, and the backend. Each runs
in its own layer with its own contract.

## 2. One producer per artifact

The classical core produces the control packet. Nothing else does. The
substrate consumes it read-only.

## 3. Invariants are owned, not shared

Volume preservation is owned by the core. Parity hysteresis is owned by the
core. Moment-band and abstention are owned by the substrate. Owners are
never overridden by downstream layers.

## 4. Frozen interfaces

Once a schema, threshold, or state machine is frozen, downstream documents
consume it by reference. They do not restate it. Restating invites drift.

## 5. Falsifiable acceptance

Every acceptance test has a numeric pass criterion declared before the run.
A run without declared thresholds is non-conformant.

## 6. Version history in the changelog, not in filenames

Document IDs (`RES-XXX`) are stable. Evolution is tracked in `CHANGELOG.md`.
Filenames never carry version numbers.

## 7. Speculative claims stay behind measured gates

The quantum / coherence backend is downstream of a trained and measured
hybrid. No speed-up or coherence claim is made before experimental
characterization.

## Read next

- [Classical Core](../200-core/classical-core.md) — RES-200
- [Roadmap](../500-notes/roadmap.md) — RES-501