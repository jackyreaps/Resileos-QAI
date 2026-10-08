---
doc: RES-402
title: Validation
status: stable
depends_on: [RES-401]
referenced_by: [RES-500]
---

# Validation

Hybrid generative validation measures the adapter + substrate against a flat
baseline over a declared seed list, and reports conformance against `(X, Y)`.

## Conformance rule

A run is non-conformant if `X` and `Y` are not declared in the run config
before execution.

## Metrics

On the declared seed list, per seed:

- NRMSE of the hybrid model
- NRMSE of the flat baseline
- NRMSE reduction `= 100 · (nrmse_flat − nrmse_hybrid) / nrmse_flat`
- Horizon of the hybrid model
- Horizon of the flat baseline
- Horizon extension `= horizon_hybrid − horizon_flat`

Aggregated:

- mean and std of NRMSE reduction
- mean and std of horizon extension

## Pass criterion

    mean(nrmse_reduction) >= X
    mean(horizon_extension) >= Y

Both must hold. The seed list is fixed and recorded.

## Per-step logging (five-tuple)

Every step logs:

    (reconstruction_rel_error, scar_energy, ΔS, μ, |log10|det J||)

Plus:

- `F_res` (continuous residual flux)
- `sigma1_action` (`"NONE"` when the gate did not fire)
- gate state from the abstention machine

## Adapter acceptance

The adapter's own acceptance tests (RES-301) run before the validation
harness:

- `0.1 < cos(μ_hv, ν_hv) < 0.5`
- drift-ratio variance above `drift_ratio_floor`
- drift-ratio SNR logged

A validation run does not proceed unless adapter acceptance passes.

## Output

The harness writes a JSON report containing:

- the full run config
- per-seed diagnostics
- aggregate statistics
- the conformance flag
- the step log

## Read next

- [Behavioral Notes](../500-notes/behavioral.md) — RES-500
- [Roadmap](../500-notes/roadmap.md) — RES-501
