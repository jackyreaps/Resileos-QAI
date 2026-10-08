---
doc: RES-400
title: Run Configuration
status: stable
depends_on: [RES-302, RES-303]
referenced_by: [RES-401, RES-402]
---

# Run Configuration

Every conformant run must emit a run config **before execution**. A run
without a declared config is non-conformant.

## Template

    packet_version:      "1.0.0"
    dim:                 # hypervector dimension
    seeds:
      factor:
      scale:
      scar:
      monitor:
      permute_uv:        # or derived = base + 0
      permute_scar:      # or derived = base + 1
      permute_scale:     # or derived = base + 2
      permute_mon:       # or derived = base + 3
    N_warm:              512
    E_sat:
    E_sigma:             # default = E_sat
    tau_sat:
    tau_low:
    sigma1_k:            3
    X:                   # NRMSE reduction %
    Y:                   # horizon extension steps
    seed_list:           [...]
    repulse_hold:        # optional hold counter
    volume_escalation:   "sigma1_CLEANUP"
    shift_monitor:
      kind:              rolling_DeltaS_var | F_res_stat
      window:            256
      trigger:           2.0
    scar_var_floor:      # declared before training
    deltaS_range_floor:  # declared before training
    drift_ratio_floor:   # declared before adapter acceptance

## Seed derivation rule

If the derived form is used: `permute_* = base_seed + offset` with offsets
frozen as `{0, 1, 2, 3}`. Either the expanded block or the derived rule must
be present; both are valid.

## Declared-before-run requirements

The following fields must be present and non-null **before** execution:

| Field | Purpose | Enforced by |
|---|---|---|
| `X` | NRMSE reduction threshold | RES-402 |
| `Y` | Horizon extension threshold | RES-402 |
| `scar_var_floor` | Training acceptance | RES-401 |
| `deltaS_range_floor` | Training acceptance | RES-401 |
| `drift_ratio_floor` | Adapter acceptance | RES-301 |

## Shift monitor semantics

`kind: rolling_DeltaS_var` — variance ratio; `trigger` is a multiplier on
warm-up variance.
`kind: F_res_stat` — statistic on signed flux; `trigger` is an absolute
multiplier on the warm-up statistic.

The config loader must record which interpretation was used.

## Example

See [`configs/example-run.json`](../../configs/example-run.json).

## Read next

- [Training](training.md) — RES-401
- [Validation](validation.md) — RES-402
