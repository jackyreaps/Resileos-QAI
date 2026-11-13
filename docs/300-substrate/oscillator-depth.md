# Oscillator depth

`KuramotoField` in `src/resileos/substrate/oscillator.py` is a stack of phase vectors. The numbers for φ, the recovery scale, the phase per debt quantum, and the outward weight are in `src/resileos/substrate/suite_constants.py`.

## Depth

The default depth is 2. Level 0 is the inner vector. Each higher index is the next level outward. Construction rejects `depth < 2`, `r < 2`, and any `orientation` other than `"outward"`.

## Within a level

On one level the phase derivative is

    dθ_i/dt = ω_i + κ / (α + ε) · sum_j W_ij sin(θ_j − θ_i)

Level 0 uses the ladder selected at construction (`golden_powers` or `golden_weyl`). Outer frequencies are that inner ladder times φ^{−level}:

    ω^(level) = ω · φ^(−level)

## Outward coupling

Coupling between levels is outward only. Level L−1 drives level L. The outer level does not drive back. The term added on level L is

    w · κ / (α + ε) · sin(θ_(L−1) − θ_L)

At the default scale, `w` is φ^{−1}. The field reads `w` from `outward_weight(scale)`. `outward_weight(1.0)` returns φ^{−1}. A different scale multiplies that weight, so the healing factor can be passed in without editing the integrator. The default scale is 1, and that leaves the outward step at φ^{−1}.

## Public state

`theta` is the level-0 phase vector and has shape `(r,)`. `order_parameter()` is the order parameter of that vector:

    R = (1/r) |sum_j exp(i · θ_j)|

`level_phases` reads one level. `depth_order()` is the mean of the per-level order parameters.

## Orientation

`velocity()` returns dθ/dt on the `r` level-0 oscillators. That is the vector the inner step uses, and it is what a caller uses when phase motion should pick a direction. A difference taken along the oscillator index is a different axis. The field does not orient by that index gradient.

## Step size

Each step is RK4. The #14 RK4 subdivider is only a safety when a within-level step would move a phase by more than 0.2 rad: when |κ / (α + ε)| times the maximum row sum of |W| times dt is greater than 0.2, that step is split so each substep stays within the bound (the existing substep cap still applies). The subdivider does not order the field. Ordering is the sine coupling, inside a level and outward between levels. A cross-level order measurement can run with the subdivider idle.

## Constants

| Name | Value | Role |
|---|---|---|
| `PHI` | (1 + sqrt(5)) / 2 | address base and outward-weight base |
| `HEALING` | 39.5 | recovery scale |
| `MAGNETIC_PHASE` | 5.116 | phase per debt quantum |
| `outward_weight(1.0)` | φ^{−1} | default outward weight; `scale` multiplies it |

`PHI` is the golden-ratio value already used for the ladder and for φ^{−level} addresses. `HEALING` is the recovery scale already stored as 39.5. The default field path calls `outward_weight(1.0)`. `HEALING` is applied by passing it as `scale`. `MAGNETIC_PHASE` is the phase constant on the same module.
