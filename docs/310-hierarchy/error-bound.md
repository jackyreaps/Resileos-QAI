doc: RES-314
title: Error Accumulation Bound
status: draft
depends_on: RES-310, RES-313
referenced_by: RES-315

# Error Accumulation Bound

A single-window round-trip at `dim = 512`, `window = 64` recovers 91% of tokens
exactly. At depth, errors compound. This document states the accumulation
model, the bound it implies, and the redundancy contract that follows from it.
It does not define an error-correcting code. It defines the bound such a code
would need to satisfy.

## 1. Single-level error

Let `p_1` be the per-token probability of exact recovery at depth 1. From the
current build at `dim = 512`, `window = 64`:

    p_1 = 0.9143

At `window = 32`, the Greek run gives `p_1 = 0.9985`. The difference is bundle
size: larger windows mean more items per bundle, more crosstalk, lower `p_1`.

## 2. Depth accumulation

A token at depth `L` is recovered by descending `L` levels. Each level adds
crosstalk from its bundle. Under the assumption that per-level errors are
independent (which they are not, but the bound is stated under this assumption
for tractability):

    p_L = p_1^L

At `p_1 = 0.9143` and `L = 4`:

    p_4 = 0.9143^4 = 0.699

At `L = 8`:

    p_8 = 0.9143^8 = 0.489

At `L = 16`:

    p_16 = 0.9143^16 = 0.239

The independence assumption is optimistic. In practice, crosstalk at depth `L`
correlates with crosstalk at depth `L-1` because the bundles share items. The
true `p_L` is lower.

## 3. The correlated model (falsified)

**This model is falsified by the empirical result `p_1 = 0.9143` at
`dim = 512`, `window = 64`. It is included only to show which standard
accumulation model does not apply. The derivation below predicts no error at
depth 16; the measured value at depth 1 is already 0.9143. Do not use this
section as a bound.**

Under the geometric-sum crosstalk model of RES-313 §2, the SNR at depth `L` is:

    SNR_L = 1 / (n_0 / D) / (1 - n_max / D)^L

The exact-recovery probability under the random-phase model is:

    p_L = Phi(SNR_L)

where `Phi` is the standard normal CDF. For `SNR_L` large, `p_L -> 1`. For
`SNR_L` small, `p_L -> 0.5` (chance, since cleanup is a nearest-neighbor lookup
over a finite codebook).

At `dim = 512`, `n_0 = 64`, `n_max = 64`:

    n_0 / D = 0.125
    1 - n_max / D = 0.875
    SNR_L = (1 / 0.125) * (1 / 0.875)^L = 8 * 1.143^L

At `L = 1`: `SNR = 9.14`, `p_1 = Phi(9.14) = 1.0` (saturated).
At `L = 8`: `SNR = 8 * 1.143^8 = 21.1`, `p_8 = 1.0`.
At `L = 16`: `SNR = 8 * 1.143^16 = 55.6`, `p_16 = 1.0`.

This model predicts *no* error accumulation at these parameters. That
contradicts the independence model in §2 and the empirical 91% at `L = 1`. The
discrepancy is because the random-phase model assumes the bundle is a sum of
independent random phasors. In practice, the codex's phasors are deterministic
and the positions are correlated. The model is wrong, and the error is not
crosstalk — it is a systematic position-binding effect.

## 4. What the bound should be

The empirical facts:

- `p_1 = 0.9143` at `dim = 512`, `window = 64`.
- `p_1 = 0.9985` at `dim = 512`, `window = 32`.
- The error is not uniform across positions. The first few positions recover
  exactly; later positions degrade.

The error model that fits is:

    p_1(pos) = f(pos / window)

where `f` is a decreasing function, near 1 for `pos << window` and near 0.5
for `pos -> window`. The window-length dependence (32 vs 64) is consistent with
this: doubling the window adds positions at the tail where `f` is small.

Under this model, the depth-`L` error is:

    p_L(pos) = f(pos / window)^L

and the expected exact-recovery rate over a uniform position distribution is:

    E[p_L] = (1 / window) * sum_{pos} f(pos / window)^L

For `f(x) = 1 - x`:

    E[p_L] = 1 / (L + 1)

At `L = 1`: `E[p_1] = 0.5`. Too low (empirical is 0.91).
For `f(x) = exp(-x)`:

    E[p_L] = (1 - exp(-L)) / L

At `L = 1`: `E[p_1] = 0.632`. Still low.
For `f(x) = 1 - x^2`:

    E[p_L] = (1 / (2L + 1)) * something

None of these fit `p_1 = 0.91` cleanly. The empirical `f` is closer to 1 for
most positions and drops sharply near the end. A piecewise model would fit, but
it would not be a bound.

## 5. The honest statement

There is no closed-form bound in this document. The empirical error model does
not match any of the standard accumulation models (independent, geometric,
exponential). The bound is therefore stated as a measurement contract:

    error_at_depth(L, dim, window) -> float

is a function the build must measure, not derive. RES-313's capacity law
predicts the *mean* behavior; this document's contract is that the
*distribution* of errors across positions and depths is measured and reported.

## 6. Redundancy contract

For a downstream consumer (RES-315) that requires a stated accuracy floor, the
build offers one redundancy mechanism: repeated encoding with different
position salts. If a token is encoded at two positions with independent salts,
the probability that both fail is `(1 - p_1)^2`, assuming independence.

The contract is:

    redundancy_factor r -> effective_p = 1 - (1 - p_1)^r

At `p_1 = 0.9143` and `r = 2`:

    effective_p = 1 - (0.0857)^2 = 0.9927

At `r = 3`: `0.9994`.

This is the only redundancy mechanism defined. It is not an error-correcting
code. It is a repetition scheme, and it costs `r` times the storage and
compute.

## 7. Non-claims

- No closed-form bound. The error model is empirical.
- No error-correcting code. Repetition is not ECC.
- No claim that independence holds. The redundancy contract assumes independent
  failures, which is optimistic.
- No downstream accuracy claim. Whether `effective_p = 0.9927` is sufficient
  for a consumer is RES-315's problem.

## 8. Open questions

- **The position-error curve.** Measure `p_1(pos)` for `pos = 0..window-1` at
  each `(dim, window)`. Fit a model. This is the missing input for any bound.
- **Depth correlation.** Measure `p_L(pos)` at each depth. Check whether the
  per-level errors are independent. If not, the redundancy contract's `r`
  factor is wrong.
- **Salt independence.** Are position salts at different levels truly
  independent? RES-310 §3 says yes by construction. Measure the cross-
  correlation to confirm.
