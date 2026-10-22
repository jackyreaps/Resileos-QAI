doc: RES-317
title: SDM + Hopfield Attractor Memory
status: draft
depends_on: [RES-200, RES-306, RES-313]
referenced_by: []

# SDM + Hopfield Attractor Memory

A parameter-free cleanup layer that sits between VSA unbinding and
codex lookup. Reduces crosstalk during multi-step sequential chain
unrolling without adding trainable parameters.

Implements item 2.1 of the Hardened Roadmap (RES-502).

## 0. Why this layer exists

Multi-hop chain evaluation in Titanos (`chain(start, [r1, r2, ...])`) is
strictly sequential. Each hop does `retrieved = band * probe`, then
`argmax(codebook @ retrieved)`. After the first hop, `retrieved` is not
a clean bound vector — it carries crosstalk from every other fact that
shares the relation band. By hop three, crosstalk often exceeds the
signal.

The substrate's capacity bound (RES-313) says this is expected: a flat
bundle of `n` items has `E|noise|² = n / dim`. At `n = 1000` and
`dim = 10,000`, SNR is ~10. At `n = 10,000`, SNR is ~1.

The attractor layer does not extend the capacity bound. It reduces the
*consequence* of crosstalk by snapping each retrieved vector to the
nearest stored pattern, so error does not accumulate as fast across
chain steps.

## 1. Two layers

| Layer | Reference | Role | Parameters |
|---|---|---|---|
| Kanerva SDM | Kanerva 1988 | Sparse neighborhood averaging | 0 |
| Modern Hopfield | Ramsauer et al. 2020 | Softmax attention snap | 0 |

Combined as `AttractorMemory.cleanup(query)`:

    noisy query
        │
        ▼
    KanervaSDM.read       — k nearest hard locations, contents summed
        │                    Averaging reduces per-component noise.
        ▼
    ModernHopfield.relax  — softmax attention over stored patterns
        │                    Deterministic snap to nearest pattern.
        ▼
    clean vector

## 2. Kanerva SDM

Fixed random bipolar address matrix of shape `(n_locations, dim)`.
Contents accumulator of the same shape, initialized to zero.

**Write(v):** find the `k` hard locations nearest to `v` by dot-product
similarity; add `v` to each of their content vectors.

**Read(q):** find the `k` nearest to `q`; sum their contents; re-binarise
to ±1 via `np.where(summed >= 0, 1, -1)`.

The read is a neighborhood average over the query's sparse address-space
vicinity. If `q` is close to a stored pattern, most of its `k` neighbors
carry that pattern; the sum is dominated by it, and re-binarization
recovers the pattern with reduced noise.

## 3. Modern Hopfield

Continuous relaxation with softmax attention. Given stored pattern
matrix `X` (shape `(n_patterns, dim)`):

    x_{k+1} = X^T · softmax(β · X · x_k / dim)

Iterate until `||x_{k+1} - x_k|| < tol` or `max_iters` reached. The
attention weights are computed with a numerically stable softmax
(max-shift before exponentiation).

**Convergence.** For clean inputs, `x_0 = X[i]` is a fixed point
(idempotent). For noisy inputs, the update pulls `x` toward the
attention-weighted average of nearby patterns, then reweights; at
sufficient `β` it converges to a specific pattern.

**β.** Inverse temperature. `β = 8` is the default (gentle snap,
preserves soft neighborhood structure). `β = 32` is sharp (aggressive
snap, may lock onto a single pattern early). Tune empirically.

## 4. AttractorMemory

The combined class. `store(v)` writes to both layers and appends to the
pattern list. `cleanup(q)` runs SDM-read then Hopfield-relax.

    mem = AttractorMemory(
        SDMConfig(dim=10_000, n_locations=4096, k_activate=64, seed=0),
    )
    mem.store_many(fact_vectors)
    cleaned = mem.cleanup(noisy_retrieved)

No gradient, no optimizer, no `.parameters()`. The updates are closed-
form. The stored contents grow monotonically with writes; there is no
eviction.

## 5. Cost

Per cleanup:

| Stage | FLOPs |
|---|---|
| SDM read | `n_locations · dim` (similarity) + `k · dim` (sum) |
| Hopfield relax | `n_patterns · dim · max_iters` |

At `n_locations = 4096`, `dim = 10,000`, `k = 64`: SDM read is
~4.1 × 10⁷ FLOPs per query. At `n_patterns = 1000` and `max_iters = 8`:
Hopfield is ~8 × 10⁷ FLOPs. Total ~1.2 × 10⁸ FLOPs per cleanup — under
1 ms on a modern CPU, or a few hundred microseconds on GPU.

Compare: the underlying `chain` hop (band multiply + codebook argmax) is
~2 × 10⁸ FLOPs at the same dim. The attractor roughly doubles per-hop
cost in exchange for reduced error accumulation. Whether that trade is
worth it depends on the chain length and the crosstalk level.

## 6. Interaction with codex cleanup

The attractor does not replace codex cleanup. The pipeline is:

    band * probe  →  AttractorMemory.cleanup  →  codex argmax  →  token_id

For a query where `band * probe` is already close to a stored fact,
`cleanup` is near-idempotent and the final argmax returns the same
token. For a noisy `band * probe`, `cleanup` may move the vector back
toward the correct fact, and the argmax then returns a token the raw
path would have missed.

Whether this improves accuracy in practice is measured by the crosstalk
benchmark in `tests/test_sdm.py::test_attractor_reduces_crosstalk_in_chain`.

## 7. Non-claims

- Not a capacity extension. The substrate still carries at most
  `C(dim)` items per bundle (RES-313). The attractor reduces error
  *given* the crosstalk, not the crosstalk itself.
- Not a substitute for codex cleanup. The final token lookup is still
  against the codebook.
- Not trainable. No gradients, no parameters. The rule is closed-form.
- Not a hierarchy replacement. Multi-hop chains are still sequential;
  parallel unfolding is out of scope (RES-502 §1.2).
- Not a physics claim. "Attractor" is used in the dynamical-systems
  sense (fixed points of an iterative map), not as a claim about any
  underlying physical substrate.

## 8. Falsification

The layer is worth keeping if `test_attractor_reduces_crosstalk_in_chain`
shows a measurable improvement over raw cleanup. If the improvement is
zero, the layer is not pulling its weight and should be removed from the
chain path.

The test constructs a synthetic band with 64 facts across 16 codebook
items at `dim = 256`, does 20 trials of `band * bound → cleanup`, and
compares `attractor_pick == j_actual` against `raw_pick == j_actual`.
If the same, the attractor is not helping at this crosstalk level.

## 9. What's missing

- **Empirical validation on real Titanos facts.** The test is synthetic;
  real crosstalk may differ.
- **Eviction policy.** Contents accumulate forever; there is no decay,
  no eviction. A "hot" pattern written 100 times will dominate the
  neighborhood.
- **β and k tuning per workload.** Defaults are chosen for `dim = 256`;
  at `dim = 10,000` the balance between SDM averaging and Hopfield snap
  may shift.
- **Chain-level benchmark.** The test is per-hop; a full chain error
  rate (fraction of 3-hop chains that land on the correct final answer)
  would be more representative.

## 10. Read next

- [Phasor Graph](phasor-graph.md) — RES-306
- [Composition Capacity Law](../310-hierarchy/capacity-law.md) — RES-313
- [Hardened Roadmap](../500-notes/hardened-roadmap.md) — RES-502
- [Documentation Index](../readme.md)
