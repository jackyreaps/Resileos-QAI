---
doc: RES-303
title: Sigma-1 Safety Gate
status: stable
depends_on: [RES-302]
referenced_by: [RES-402, RES-500]
---

# Sigma-1 Safety Gate

The sigma-1 gate is a deterministic regime switch driven by the same
monitors already present in the control packet. It fires before the
abstention machine's decision is finalized.

## Triggers (frozen)

- scar energy `> E_sigma` (default `E_sigma = E_sat`; may be set higher)
- `μ` transition while scar energy `> E_sigma / 2`
- `volume_ok == False` for more than `k = 3` consecutive steps

## Priority order (immutable)

When the gate fires, exactly one action is selected:

1. `CLEANUP` — full re-encoding
2. `REEMBED` — hierarchical re-embedding of residual scales
3. `REPULSE_ABSTAIN` — raise repulsion and return `ABSTAIN`

Thresholds may be tuned per experiment. The order itself is immutable.

## Precedence versus abstention

    if sigma1_gate:
        use sigma1_action
    elif not volume_ok:
        ABSTAIN
    else:
        abstention state machine

`sigma1_action` is written into the packet for that step. `sigma1_gate` is
set to `true` for that step; `false` otherwise.

## Persistence

`sigma1_action = REPULSE_ABSTAIN` holds until the next sigma-1 evaluation or
an explicit reset by the gate. The evaluation cadence is declared in the run
config (RES-400).

## Read next

- [Behavioral Notes](../500-notes/behavioral.md) — RES-500
- [Validation](../400-operations/validation.md) — RES-402