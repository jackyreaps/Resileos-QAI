doc: RES-607
title: Spectral Skeleton
status: conjectural
depends_on: [RES-200, RES-306, RES-312, RES-600, RES-601]
referenced_by: [RES-604]

# Spectral Skeleton

The QD-TER bridge (RES-600 through RES-606) is expressed in the
language of finite spectral triples. The Resileos-QAI substrate already
contains the discrete ladders that would determine the spectrum of such
a triple, if the mapping holds. This document names that discrete data
and defines a module that exposes it.

It does not claim the mapping is an isomorphism. It claims the skeleton
is well-defined, that it has no continuous parameters, and that a
specific test would determine whether it is the correct input to the
metric bridge.

## 0. Status

The canonical metric bridge (`BridgeMetricHead` in
`src/resileos/substrate/geometry.py`) remains locked. RES-606 gives
candidate closed forms for its four open items as a *tuning* path; this
document gives a *structural* path. Neither path unlocks the head. They
are complementary: RES-606 is what to try now, RES-607 is what to
derive if the candidate forms fail to generalize.

## 1. What the skeleton is

The skeleton is the discrete combinatorial data that determines the
residual Dirac operator `D_res`. It is not `D_res` itself. It is not
the metric. It is the input from which both are computed.

The skeleton is a function of existing substrate constants only. No
continuous parameter is introduced. Every entry is either:

- an existing constant (`ε = 1/64` from RES-200); or
- a value computed from one of the discrete ladders already used by the
  substrate (golden ladder, prime tower, primorial Nyquist bound,
  rank folds, mask-stack weights).

## 2. Contents

| Entry | Source | Value |
|---|---|---|
| ε-ladder | RES-200 residual grid | `ε = 1/64` |
| golden ladder | `KuramotoField`, `ladder="golden_powers"` | `ω_k = ω_base · φ^k` |
| prime tower | RES-312 Cipolla-normalised primes | `p_2, p_3, p_4, …` |
| primorial Nyquist | RES-312 extension | `P_k < dim/2` |
| rank folds | φ-compress contraction | integer sequence |
| mask-stack weights | RES-312 layer schedule | `1/(l+1)` |

The skeleton exposes these as methods. It does not claim they are
independent; some are functions of others (the primorial bound is
determined by the prime tower, for instance).

## 3. The cascade

`cascade()` walks the skeleton and emits a spectrum — a pair of arrays
`(eigenvalues, multiplicities)`. The composition rule is a design
choice, not a derivation. Two strategies are provided:

**`"golden_x_prime"`** — eigenvalues are the product of the golden
ladder and the prime ladder, truncated to the shorter length.
Multiplicities are 1.

    λ_k = ω_base · φ^k · p_{k+2}     for k = 0..min(n_golden, n_primes)-1
    m_k = 1

**`"golden_with_prime_mult"`** — eigenvalues are the golden ladder,
multiplicities are the prime ladder truncated to the same length.

    λ_k = ω_base · φ^k
    m_k = p_{k+2}

Neither is claimed to be the correct composition. They are two specific
choices that make the skeleton operational. A different composition is
a different design decision, and the module supports adding it.

## 4. Spectrum output

`cascade()` returns a `SkeletonSpectrum` with:

- `eigenvalues` — 1-D `float64`, non-negative
- `multiplicities` — 1-D `int64`, each ≥ 1
- `trace` — `Σ λ_i · m_i`
- `highest_mode` — `max(λ)`, the natural UV cutoff

The trace is the skeleton's spectral action at zeroth order. The
highest mode is the natural truncation scale. Neither is claimed to be
the physical value of anything; they are derived quantities of the
skeleton.

## 5. What this does not claim

- **Not a metric.** The skeleton produces a spectrum. The bridge from
  spectrum to metric `g_ij` is a separate consumer. `SpectralSkeleton`
  does not compute `g_ij`, and `BridgeMetricHead` is not unlocked by
  its existence.
- **Not unique.** Two different composition strategies produce two
  different spectra from the same ladders. The skeleton does not
  privilege either.
- **Not physics.** The word "spectral" is used in the mathematical
  sense (Connes' NCG), not as a claim about physical spacetime.
- **Not a strict spectral triple.** The strict object requires
  additional structure (real structure `J`, grading `γ`, order-one
  condition). The skeleton is the discrete input; it is not the triple.
- **Not a replacement for RES-606.** The candidate closed forms in
  RES-606 remain the tuning path. The skeleton is the structural path.
  If RES-606's candidate generalizes, the skeleton is unnecessary. If
  it does not, the skeleton is the derivation to try.

## 6. Falsification targets

In order of cost:

1. **Ladder equivalence.** Compute the golden ladder and the prime
   ladder. Ask whether there is a monotone change of variable mapping
   one to the other up to a multiplicative constant. If yes, the two
   are views of the same spectrum and the composition rule is
   constrained. If no, they are independent ladders and `D_res`'s
   spectrum is not determined by either alone.

2. **Trace consistency.** Compare the skeleton's `trace` to the
   residual core's observed spectral data (energy sums, scar-matrix
   traces). If the numbers are unrelated at every scale, the skeleton
   is not the correct input.

3. **Metric comparison.** Construct a metric from the skeleton
   (form unspecified here) and compare to RES-606's candidate
   `g_ij = δ_ij · [1/(1+Re) + G·m_0/(φ_B−φ_A)]` on the same monitors.
   If they agree where both are defined, the skeleton is at least
   consistent with the candidate. If they disagree, one of the two is
   wrong.

4. **No-free-moduli check.** Enumerate every constant in the pipeline
   (`τ`, `k`, `p`, `g_0`, `g_ramp`, `κ`, `α`, ε, tower exponents,
   mask-stack weights). For each, classify as (a) determined by the
   skeleton, (b) a computational hyperparameter outside the metric, or
   (c) a continuous free parameter of the metric. If any constant
   falls in (c), the no-free-moduli claim fails.

## 7. Implementation

The module is `src/resileos/substrate/spectral_skeleton.py`. It exposes:

    SpectralSkeletonConfig   # discrete ladders
    SpectralSkeleton         # the skeleton object
    SkeletonSpectrum         # (eigenvalues, multiplicities)

`SpectralSkeleton.cascade()` returns a `SkeletonSpectrum`. The skeleton
reads the prime tower (RES-312) and the codex's `PHI` constant. It
writes nothing.

## 8. Open questions

- **Correct composition.** Which of the two strategies, if either, is
  the right one? A third strategy (Kronecker product, tensor sum, or a
  different pairing) may be correct. The skeleton does not decide.
- **Multiplicity structure.** In `"golden_x_prime"`, multiplicities
  are all 1. This makes the skeleton a pure eigenvalue list. Whether
  the multiplicities should encode the mask-stack weights or the
  primorial structure is not settled.
- **UV cutoff.** The `highest_mode` is the largest eigenvalue of the
  skeleton. Is this the correct UV cutoff, or should the cutoff be a
  topological index (an integer) derived from the skeleton's structure?
- **Relation to Operator-M.** The QD-TER side calls its object
  Operator-M. The skeleton is a candidate for the discrete input to
  Operator-M. The bridge between the two is the subject of RES-601 §7.

## 9. Read next

- [FEP Reduction Bridge](fep-reduction.md) — RES-600
- [Non-Dual Adaptation Layer](non-dual-adaptation.md) — RES-601 §7
- [Metric Bridge Candidate Derivations](metric-bridge-derivations.md) — RES-606
- [QD-TER Bridge Status](status.md) — RES-604
