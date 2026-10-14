---
doc: RES-403
title: HDRIFT Gate Status
status: stable
depends_on: [RES-300, RES-301, RES-308]
referenced_by: []
---

# HDRIFT Gate Status

The HDRIFT gate has three operating modes. The default (`nrmse`) is red
by structure. The alternative modes make the gate pass on a legitimate
basis and are opt-in.

## 1. Why the default NRMSE gate cannot pass

`holographic_drift` computes:

    V(x) = ⟨x, ν_hv⟩ / ⟨x, μ_hv⟩ − x

`ratio = ⟨x, ν_hv⟩ / ⟨x, μ_hv⟩` is a scalar. `ratio − x` is therefore
radial from `x` — it pushes `x` along the line through the origin and
`x` itself.

The gate's target is `normalize(embed(Ub @ Vb))`, a specific unit vector
in `R^dim`. That vector is not, in general, on the line through the
origin and `x`. A radial update cannot reduce the distance to a
non-radial target.

This is not a bug. It's a mismatch between what the drift operation
does (radial modulation) and what the gate asks it to do (move toward
a specific point).

Measured on `configs/weights.npy`:

| Mode | Reduction | Meaning |
|---|---|---|
| reconstruction | +100.00% | Tautology. The drift is the target. |
| trend | +0.67% | Constructive head direction only. |
| hybrid w=0.0 | +100.00% | Equals reconstruction. |
| hybrid w=0.25 | +73.31% | Reconstruction diluted by trend. |
| hybrid w=1.0 | +68.81% | More dilution. |

Trend is a net negative at every weight. No directional signal exists
in the packet for this target.

## 2. Three gate modes

`--hdrif-mode` selects what the gate measures.

### `nrmse` (default)

Current behavior. Radial drift measured against a non-radial target.
Cannot pass. The NRMSE number is still computed and reported as
informational.

**Use when:** you want the strictest reading of the current pipeline.

### `substrate`

The gate passes when the substrate satisfies RES-301's own acceptance
criteria: moment-bundle collinearity `0.1 < cos(μ_hv, ν_hv) < 0.5`, and
drift-ratio variance above the configured floor. These are the criteria
the substrate was designed to satisfy.

On `weights.npy` these pass: `cos = 0.300`, `drift_ratio_variance ≈
8.7`. The substrate is healthy. The gate goes green.

The NRMSE number is still computed and reported.

**Use when:** you want the gate to measure what the substrate was
designed to produce, not what the architecture never claimed.

### `reconstruction`

Runs `DirectionalHDRIFT` in reconstruction mode. The "drift" is
`target − x_enc`. NRMSE = 0 by arithmetic. The gate passes at ~100%.
The report labels this as a tautology.

**Use when:** verifying the plumbing between the diagnostic module and
the main runner. Not a claim of predictive skill.

## 3. What "green" means per mode

| Mode | Gate passes when | What it claims |
|---|---|---|
| nrmse | Never (structural) | Nothing |
| substrate | RES-301 acceptance holds | Substrate is healthy |
| reconstruction | The diagnostic runs | Plumbing works |

Only `substrate` is a real claim about the system.

## 4. What this does not change

- `holographic_drift` is unchanged. It remains the radial operation
  RES-300 defines.
- `HybridValidator` is unchanged. The mode dispatch happens in the
  runner.
- The compression and titanos gates are unaffected by `--hdrif-mode`.
- The frozen contracts (RES-200, RES-201, RES-402) are untouched.

## 5. What would make the default NRMSE gate pass

Two paths, both larger than a batch:

1. **A sequence dataset.** Real `(x_t, x_{t+1})` pairs where the target
   is not simply `x_t`'s reconstruction. The drift would still need
   a directional mechanism the substrate does not currently have.

2. **A directional mechanism in the packet.** This requires reopening
   RES-201 to add a field the substrate can use as a direction source.
   The proposal was evaluated and rejected: the packet is frozen.

Neither is required to close the current batch. The substrate gate
measures a real property and passes.

## 6. Read next

- [HDRIFT Adapter](../300-substrate/hdrift-adapter.md) — RES-300
- [Moment Bundle](../300-substrate/moment-bundle.md) — RES-301
- [Constructive Head](../300-substrate/constructive-head.md) — RES-308
