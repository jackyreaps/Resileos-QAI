---
doc: RES-401
title: Training
status: stable
depends_on: [RES-400]
referenced_by: [RES-402]
---

# Training

Residual-compensation training makes scar energy and `ΔS` informative so the
abstention and sigma-1 machines become useful.

## Scope — frozen core vs trainable front-end

**Frozen core (never receives gradients):**

- Jacobian
- Scar update `Λ`
- Volume guard
- Prime-Tower schedule
- Residual-flux parity invariant

**Trainable front-end only:**

- The encoder that produces `Ub`, `Vb`, `row_s_k`, `col_s_k`, `lat_s_k`
  from inputs.

Gradients are prohibited from entering `Λ`, the volume guard, or the
schedule. This preserves the sole-producer rule (RES-102 §2) while allowing
the front-end to be trained.

## Loss

    L = reconstruction_error
      + λ · residual_scale_regularization(k)

The regularization acts on the integer exponents `k` on the ε-grid.

## Quantization-aware training (QAT)

Binary factors `Ub`, `Vb` are trained with a QAT schedule so that binarization
at inference matches the trained regime. The QAT schedule must be recorded in
the run config.

## Logging

After every epoch, log the five-tuple:

    (reconstruction_rel_error, scar_energy, ΔS, μ, |log10|det J||)

Plus `F_res` and, when the sigma-1 gate fires, `sigma1_action`.

## Acceptance

A training run is non-conformant if `scar_var_floor` and
`deltaS_range_floor` are not declared in the run config before training
begins.

Both floors must be met on the held-out seed list after the final epoch:

- scar-energy variance ≥ `scar_var_floor`
- `ΔS` dynamic range ≥ `deltaS_range_floor`

## Read next

- [Validation](validation.md) — RES-402
- [Behavioral Notes](../500-notes/behavioral.md) — RES-500
