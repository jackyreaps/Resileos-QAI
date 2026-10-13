---
doc: RES-306
title: Phasor Graph
status: stable
depends_on: [RES-200]
referenced_by: [RES-305]
---

# Phasor Graph

A graph whose edge weights are complex phasors, with band carriers
supplied by unit-phasor vectors over the substrate dimension. A
companion memory structure (`BandedMemory`) stores key-value pairs
across bands.

This is an **optional data structure**. It does not replace `Λ` in the
residual core by default. When used to construct a coupling for the
core, the acyclic variant preserves `det(I + strict_lower) = 1`.

## 0. Formal verification

The structural claims in this document are formally verified in the
`OscGraph` Lean package (six modules: `Phasor`, `Topology`,
`Laplacian`, `Sampling`, `Golden`, `Crosstalk`), built with no `sorry`,
using only `propext`, `Classical.choice`, and `Quot.sound`.

Each claim below is marked:

- **[proved]** — named theorem in `OscGraph`
- **[standard]** — textbook fact
- **[proposal]** — design suggestion

The Lean sources are not yet committed to this repository. Theorem
names below refer to them by identifier.

## 1. Edge weight type

Edge `i → j` carries one complex number:

    w_ij = a_ij · e^{i φ_ij},  a_ij ≥ 0,  φ_ij ∈ [0, 2π)

Stored as one `complex128` per edge. Not a `ℂ^d` vector per edge — that
would make storage O(E · d) and every operation a per-edge tensor
multiply. Band-level phase (below) provides the directional content.

## 2. Band carriers

A band is a unit-phasor vector of length `d`:

    u_k[m] = exp(i ω_k m) / √d,   m = 0 … d−1

Binding into band `k`:

    bind(x, k)   = x ⊙ u_k
    unbind(y, k) = y ⊙ conj(u_k)

**Binding is exact** **[proved]** (`unbind_bind`, `bind_unbind`):
`unbind(bind(x, k), k) = x` componentwise. There is no permutation, no
inverse lookup, nothing else to undo. This rules out the class of bug
where a permutation is applied on one path and not the other.

## 3. Hermitian vs. triangular

Hermitian pairing: `w_ji = conj(w_ij)`.
Triangular: `w_ij = 0` for `i < j`.

**The two are incompatible (nontrivially).** A Hermitian matrix that is
also strictly upper- or lower-triangular is the zero matrix off the
diagonal.

The graph therefore offers **two adjacencies**, used for different
purposes, chosen per instantiation:

| Variant | Adjacency | Spectrum | Used for |
|---|---|---|---|
| `hermitian=True` | `A = A*` | real (Hermitian) | Laplacian, spectral analysis, memory |
| `hermitian=False` | `A` unrestricted | complex | triangular coupling for the residual core |

**Hermitian gives real spectrum** **[proved]**
(`BandGraph.adjacency_isHermitian`, `BandGraph.eigenvalue_real`).

**Triangular preserves `det J = 1`** **[proved]**
(`det_one_add_strictLower`, over any commutative ring including `ℂ`):
`det(I + strict_lower(A)) = 1`, and every eigenvalue of `J` is exactly
`1` (`spectrum_one_add_strictLower`). So `ρ(J) = 1` on any acyclic
graph, and a spectral-radius guard on `J` itself would fail on graphs
that have no cycles.

**Connection Laplacian energy is PSD** **[proved]**
(`laplacianEnergy_nonneg`, `laplacianEnergy_eq_zero_iff`): for
non-negative edge strengths and unit phases, the quadratic form
`Σ c_ij ‖x_i − u_ij x_j‖²` is `≥ 0`, and it is `0` exactly when
`x_i = u_ij x_j` on every edge of positive strength.

## 4. Carrier spacing

Carrier frequencies use a golden-ratio Weyl sequence:

    ω_k = 2π · frac(k · φ),   φ = (1 + √5) / 2

**Rational spacings recur and lock; golden ones never do** **[proved]**
(`returns_iff_rational`, `lock_iff_rational`, `golden_never_locks`,
`golden_carrier_never_returns`). Integer ratios should be reserved for
bands that are *meant* to lock.

## 5. Nyquist and the framework ladder

The substrate update period is 50 ms. Sampling Nyquist is 10 Hz.
**Frequencies above 10 Hz cannot be carried as sampled waveforms** — they
must be carried as fixed-carrier phasors.

**Aliasing and folding** **[proved]** (`sampledPhasor_alias`,
`sampledCos_fold`). **Nyquist separation** **[proved]**
(`sampledCos_injective_below_nyquist`, `nyquist_50ms`).

Only the `7.83 Hz` rung of the framework ladder is below Nyquist
(`ladder_below_nyquist`). The `16.007` and `36.017 Hz` rungs fold to
within `2π · 0.0005` rad of each other per update
(`beat_9fold_near_collision`). The caustic aliases to DC. **Golden
spacing is the default.**

## 6. The memory: crosstalk and band sharding

Two results **[proved]** in the random-phase model (uniform phases over
`m ≥ 2` levels; results do not depend on `m`):

**Coherent / incoherent split** (`incoherent_power`, `coherent_power`):
`N` independent random unit phasors have mean power exactly `N`. `N`
aligned ones have power `N²`, and no `N` unit phasors have more.

**Crosstalk `√((N−1)/D)`** (`similarity_eq_one_add_noise`,
`crosstalk_variance`): store `N = n + 1` key-value pairs in `D`
components, query with one key. The score against its value is
`1 + noise`, and with random keys, `E|noise|² = n/D` exactly.

**Band sharding by `√K`** (`band_sharding`, `band_sharding_variance`):
split `N = K(n+1)` items over `K` bands of `n+1` items each, read each
band separately at the full `D`. Per-query noise variance is at most
`1/K` of a single shared memory's.

**Caveat.** The `√K` gain assumes each band is a separate accumulator
read separately. If all bands are superposed into one `d`-vector and
read together, items in other bands are crosstalk too and there is no
gain.

## 7. Packet-field mapping

| Packet field | Graph / memory quantity |
|---|---|
| `rank` | number of active bands |
| `Lambda` entries | edge amplitudes (phases from names) |
| `mu` | edge orientation sign convention |
| `DeltaS` | phase bandwidth (spectral spread) |
| `F_res` | local velocity |
| scar energy | Laplacian energy from identity, starts at 0 |
| `volume_ok` | gate: which edges are permitted |
| sigma gate trigger | spectral margin `λ_min(L) − τ` |

## 8. Volume guard

**Acyclic (triangular) variant.** `det J = 1` **[proved]**. Volume
guard unchanged. Note the guard is a *witness* that the graph is
triangular, not a numerical stability test.

**Cyclic (feedback) variant.** Deferred. One 2-cycle with weights `a, b`
gives `det J = 1 − a·b` **[proved]** (`det_two_cycle`), and the guard
fails for example at `a·b = 1/2` (`volumeGuard_two_cycle_fails`). A
replacement guard is required before cycles are enabled.

## 9. Phase provenance

Edge phases come from a SHA-256 hash of the endpoint names, not from a
PRNG seed:

- Reloading state cannot introduce new entities.
- Two machines building from the same name set produce identical graphs.

`hash()` (Python's built-in) is not used — it is randomized per process.

## 10. What this spec does not claim

- That the phasor graph improves language modeling.
- That it enables a quantum speedup. A Hermitian matrix is a Hamiltonian
  for any matrix; graph structure matters for a speedup only if the
  specific problem is graph-structured (as in QAOA).
- That cycles in the core coupling are beneficial. Cycles are deferred.

## 11. Build order

| Step | Deliverable | Status |
|---|---|---|
| A | `PhasorGraph` + `BandCarriers` | done |
| B | `BandedMemory` | done |
| C | Triangular projection to core `Λ` | not started |
| D | Cyclic variant + new volume guard | deferred |
