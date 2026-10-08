---
doc: RES-200
title: Classical Residual Core
status: stable
depends_on: [RES-101, RES-102]
referenced_by: [RES-201, RES-202, RES-300]
---

# Classical Residual Core

The classical core is the deterministic, volume-preserving engine at Layer A.
It is the **sole producer** of the control packet and never consumes state
from the substrate.

## Responsibilities

1. Residual-compensation compression — latent factorization → binary factors
   → residual scales on the ε-grid.
2. Residual membrane `M = W − W̃`.
3. Dynamical scar update.
4. Sharpness monitor `ΔS` and residual-flux parity `μ`.
5. Unipotent hierarchical embedding of residual scales with exact
   volume-preservation guard (`|det J| = 1` by construction).
6. Prime Tower even/odd discrete schedule for residual rank.

## Residual-scale grid

| Property | Value |
|---|---|
| Quantum | `ε = 1/64` |
| Exponent range | `k ∈ [-16, +16]` |
| Representation | `int16` integer exponents |
| Scale value | `k · ε` |
| Out-of-range | clamped; clamp is logged |

## Dynamical scar

    Λ ← αΛ + βM + γF(Λ, M)

`F` is kept lower-triangular-friendly so the composite map remains unipotent.
The scar update is **frozen** — it does not receive gradients (see RES-401).

## Volume preservation

Per-step criterion:

    |log10(|det J|)| < 1e-9

Both the raw determinant and the logged quantity are recorded every step.
`volume_ok` is `true` only when the criterion holds.

`volume`, `volume_ok`, and `rank` are part of the full packet and are
advisory for the quantum / coherence backend.

## Prime Tower schedule

    rank = PrimeTower(schedule_index)

Both values are stored in the packet so replays are exact.

## Trainable vs frozen boundary

| Component | Gradients allowed |
|---|---|
| Jacobian | No |
| Scar update `Λ` | No |
| Volume guard | No |
| Prime-Tower schedule | No |
| Residual-flux parity invariant | No |
| Front-end encoder (`Ub`, `Vb`, `row_s_k`, `col_s_k`, `lat_s_k`) | Yes |

See RES-401 for the training scope and acceptance floors.

## Read next

- [Control Packet](control-packet.md) — RES-201
- [Canonicalization](canonicalization.md) — RES-202
- [HDRIFT Adapter](../300-substrate/hdrift-adapter.md) — RES-300