---
doc: RES-301
title: Moment Bundle
status: stable
depends_on: [RES-300]
referenced_by: [RES-302, RES-402]
---

# Moment Bundle

The moment bundle defines exactly how a control packet becomes two
hypervectors `(μ_hv, ν_hv)`. It is the frozen contract that makes the
adapter reproducible.

## Separate moments

| Moment | Source | Seed |
|---|---|---|
| `M_U` | `Ub.ravel()` | `factor` |
| `M_V` | `Vb.ravel()` | `factor + 1` |
| `M_scale` | `bundle(FPE(row_s_k), FPE(col_s_k), FPE(lat_s_k))` | `scale` |
| `M_scar` | `FPE(Lambda.ravel())` | `scar` |
| `M_mon` | `bind(FPE([μ]), FPE([ΔS]))` | `monitor` |

## Bundle construction

    μ_hv = bundle(M_U, M_V, M_scale, M_scar, M_mon)

    ν_hv = bundle(
        permute(M_U,  permute_uv),
        permute(M_V,  permute_uv + 1),
        M_scale_nu,
        permute(M_scar, permute_scar),
        M_mon_nu
    )

`M_scale_nu` and `M_mon_nu` use **distinct seeds** from their `μ_hv`
counterparts (`permute_scale`, `permute_mon`). This is required so that
shared components do not dominate the inner product.

## Seeds

| Seed | Purpose |
|---|---|
| `factor` | `M_U`, `M_V` |
| `scale` | `M_scale` in `μ_hv` |
| `scar` | `M_scar` in `μ_hv` |
| `monitor` | `M_mon` in `μ_hv` |
| `permute_uv` | `M_U`, `M_V` in `ν_hv` |
| `permute_scar` | `M_scar` in `ν_hv` |
| `permute_scale` | `M_scale` in `ν_hv` |
| `permute_mon` | `M_mon` in `ν_hv` |

Derived rule (accepted alternative): `permute_* = base + {0, 1, 2, 3}`.
Either the expanded block or the derived rule must be present in the run
config.

## Acceptance tests

| Test | Criterion |
|---|---|
| Collinearity | `0.1 < cos(μ_hv, ν_hv) < 0.5` |
| Drift-ratio variance | exceeds the declared floor across a fixed sample of `x_enc` |
| Drift-ratio SNR | logged (not gated) |

If collinearity falls below `0.1`, the ratio becomes noisy. If it exceeds
`0.5`, the drift loses signal. Both bounds are frozen.

## Read next

- [Abstention](abstention.md) — RES-302
- [Validation](../400-operations/validation.md) — RES-402