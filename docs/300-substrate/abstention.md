---
doc: RES-302
title: Abstention State Machine
status: stable
depends_on: [RES-301]
referenced_by: [RES-303, RES-402]
---

# Abstention State Machine

The abstention machine maps `(ΔS, μ, scar_energy, volume_ok)` to exactly one
of four states.

## States

    { CONTINUE, REPULSE, CLEANUP, ABSTAIN }

## Priority rules (frozen)

1. If `scar_energy > E_sat` or `ΔS > tau_sat` → `CLEANUP`
2. Else if `μ = 1` → `REPULSE`
3. Else if `ΔS < tau_low` → `ABSTAIN`
4. Else → `CONTINUE`

Repulsion tracks the **parity state**, not the instantaneous flux. This
avoids contradiction with the hysteresis in the parity invariant.

Repulsion is **asymmetric** by design: `μ = 0` does not trigger symmetric
repulsion.

## Parity invariant

`μ` is set by signed residual flux `F_res` with hysteresis:

    F_res > θ_hi  → μ = 1
    F_res < -θ_lo → μ = 0
    otherwise     → μ = μ_prev

Spontaneous flips are forbidden. Any observed flip logs `F_res` at the
crossing step and raises a diagnostic.

## Calibration (frozen)

| Parameter | Default rule |
|---|---|
| `θ_hi` | `q_{0.95}(F_res)` over warm-up |
| `θ_lo` | `-q_{0.05}(F_res)` over warm-up |
| `N_warm` | 512 steps |
| `E_sat`, `tau_sat`, `tau_low` | computed on the same warm-up window (absolute or quantile rule recorded) |

Distribution-shift monitor for re-calibration: rolling variance of `ΔS` over
a 256-step window; trigger when variance exceeds 2× warm-up variance.

All thresholds, seeds, and the warm-up window are logged in the run config.

## Read next

- [Sigma Gate](sigma-gate.md) — RES-303
- [Run Config](../400-operations/run-config.md) — RES-400