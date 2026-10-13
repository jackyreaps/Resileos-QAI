---
doc: RES-305
title: Causal Sandbox Index
status: proposal
depends_on: [RES-200, RES-306]
referenced_by: []
---

# Causal Sandbox Index

A scalar in `(0, 1]` measuring how closed a residual trajectory is:
how little the dynamics leak, how well they predict their own next
state, and how much they disagree with any external reference.

## 0. Status

This is a **proposal**. The metric is defined cleanly and is
deterministic, but no theorem in this repository or the OscGraph
package establishes that a high value implies anything specific about
the system. The claim is a hypothesis under test.

The general notion of finite dynamical systems forming closed causal
subsystems — with measurements internal to the dynamics — has been
discussed in relational-geometry contexts.

## 1. Definition

For a trajectory of length `T`:

    CSI_T = exp(-(1/T) Σ_t v_t)
          · exp(-(1/T) Σ_t e_t^int)
          · [1 / (1 + (1/T) Σ_t e_t^ext)]

with

| Term | Meaning | Range |
|---|---|---|
| `v_t` | volume residual: `|log10(\|det J_t\|)|` | `[0, ∞)` |
| `e_t^int` | internal prediction error: normalized step-to-step change in the monitor vector | `[0, ∞)` |
| `e_t^ext` | external discrepancy vs a supplied reference | `[0, ∞)`, or omitted |

`CSI_T ∈ (0, 1]`. `CSI_T = 1` requires zero volume residual, zero internal
prediction error, and zero external discrepancy, at every step.

## 2. Component sources in this repository

| Term | Where it comes from |
|---|---|
| `v_t` | `Packet.volume` (`|det J|`), via `volume_residual()` |
| `e_t^int` | `ResidualCore` monitor vector (e.g. `(‖Λ‖, anisotropy)`), differenced between steps, via `internal_prediction_error()` |
| `e_t^ext` | caller-supplied; omitted when no reference exists |

The monitor vector is arbitrary. Any tuple of scalar monitors with
comparable scales works; the code normalizes componentwise.

## 3. Optional living-system factor

A completely frozen system has `e_t^int = 0` at every step. Under the
plain CSI it would score highest. Whether that is desirable depends on
what "closed" is supposed to mean.

The optional living-system factor multiplies the CSI by:

    exp(-k · (mean e_int − d*)^2)

so moderate internal drift is rewarded. Defaults: `k = 4.0`, `d* = 0.1`.
This is a heuristic. It has no derivation. It is off by default.

## 4. Dual-path control

CSI is designed to gate a two-layer control:

- **Fast gut layer.** Direct unbind + cleanup on the residual memory.
  Cheap. Uses monitors, per-band noise floor, and current CSI.
- **Slow deliberate layer.** Full recurrent refinement, holographic
  drift, sigma-gate deep path. Expensive.

Decision rule:

    fast_conf = (1 - exp(-cleanup_conf / (3 σ_eff))) · CSI

    if fast_conf ≥ τ_fast:      accept the fast decision
    else:                       escalate to the slow path

with `σ_eff` the per-band effective noise floor and `τ_fast` a
configurable threshold.

Both paths preserve the one-way packet boundary: the fast layer never
reads the slow layer's state, and vice versa. Escalation is a decision
about *which* path runs, not a merge of their internal states.

## 5. What is claimed

Established (deterministic, testable):

- CSI is in `(0, 1]`.
- Volume-preserving trajectories with no internal error have CSI = 1.
- CSI is monotone decreasing in each of the three mean quantities.
- The dual-path decision is deterministic given `(state, query)`.

Not claimed:

- That high CSI implies anything physical about the system.
- That the effective-noise-floor scaling is exact.
- That the living-system factor corresponds to any natural quantity.
- That the dual-path split improves quality or reduces compute. This
  is a hypothesis under test.

## 6. Experiment hooks

When running basin experiments, log per-query:

- `v_t` sequence (per recurrent loop)
- `e_t^int` sequence
- running CSI
- fast-path decision and whether escalation occurred
- the actual answer's confidence

An ablation compares three configurations on the same workload:

| Config | Description |
|---|---|
| `conservative` | D = I, fixed thresholds, no CSI escalation |
| `emergent` | D evolves, thresholds from σ_eff, no CSI escalation |
| `dual-path` | emergent + CSI-gated escalation |

Measure: retrieval accuracy, mean loops per query, abstention rate.
The dual-path configuration should match or exceed `emergent` accuracy
while reducing mean loops. If it does not, `τ_fast` or the σ_eff
scaling needs adjustment; both are knobs, not fixed quantities.

## 7. Read next

- [Phasor Graph](phasor-graph.md) — RES-306
- [Classical Core](../200-core/classical-core.md) — RES-200
