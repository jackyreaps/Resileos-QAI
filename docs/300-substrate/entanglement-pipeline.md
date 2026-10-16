doc: RES-309
title: Entanglement Pipeline Engine
status: conjectural
depends_on: [RES-200, RES-201, RES-306, RES-308, RES-310, RES-311, RES-312]
referenced_by: []

# Entanglement Pipeline Engine

A research direction, not a component. The hierarchy pipeline (RES-310,
RES-311, RES-312) already shares prefix structure across token streams:
two sequences that agree on their first N tokens share their level-1
through level-log_c(N) buffers, and the cascade emits one shared parent
packet per shared subtree. This document states the hypothesis that this
shared-prefix structure is a *coarse-grained* view of a finer correlation
structure in the oscillator field (RES-306, RES-308), and defines the
test that would make that hypothesis falsifiable.

It does not claim entanglement. It claims that a specific measurement
would distinguish entanglement-like correlation from classical
shared-prefix structure, and that the measurement has not been run.

## 0. Quantum, precisely

**Quantum capability.** Physical superposition, entanglement,
measurement, error-corrected gates. Requires a QPU. RES-501 territory:
speculative, downstream, absent from this repository.

**Quantum-shaped mathematics.** Complex numbers, unit-modulus phasors,
unitary operators, Hermitian matrices. Runs on classical CPUs.
Deterministic. Used throughout the substrate.

The distinction is the same one RES-308 §0 makes. This document does not
move the boundary between the two. It proposes a measurement that would
report where the boundary currently is, for the specific case of the
oscillator field's phase correlations.

## 1. The pipeline structure that already exists

Three components produce correlation-like structure today:

| Component | What it does | Correlation-like property |
|---|---|---|
| `HierarchicalEncoder` (RES-310) | Bundles tokens into packets at each level | Shared prefixes produce shared parent packets |
| `StreamState` (RES-311) | Folds packets into a running hypervector | Sequential packets are entangled in the state |
| `MaskStack` (RES-312) | Re-bundles the stream along tower levels | Layers are near-orthogonal but not independent |

The first row is the one that reads as an entanglement pipeline. When two
token streams share a prefix, the encoder does not re-derive the shared
packets. The level-1 through level-L-1 packets are the same objects,
referenced by both streams. In a persistent-tree implementation (not yet
built), this would be structural sharing; in the current implementation,
it is incidental but real.

The claim in this document is that this shared-prefix structure is a
projection of a finer-grained correlation in the `KuramotoField.theta`
phase vector that drives the substrate. Under that reading, R (the order
parameter) is not merely a coherence measure — it is a coarse-grained
entanglement monotone, and the gate states map to correlation regimes:

| Gate state | R range | Phase correlation | Quantum reading |
|---|---|---|---|
| LOCKED | > 0.9 | All oscillators synchronized | Maximally correlated |
| MIXED | 0.3–0.9 | Partial correlation | Partially entangled |
| EXPLORING | < 0.3 | Oscillators independent | Product state |

That table is a hypothesis. It is the thing the test in §4 is designed
to falsify.

## 2. What is missing for the hypothesis to be testable

Four objects do not exist in the repository:

1. **Subsystem partition.** A function `partition(theta) -> (theta_A,
   theta_B)` that assigns each of the r oscillators to one of two
   subsystems. Currently the field is a single phase vector with no
   notion of subsystems.

2. **Reduced state.** A marginal over `(theta_A, theta_B)` that defines
   what "the state of A" means. For phase ensembles the natural object is
   the covariance of the phase distribution, or the Wigner transform, or
   a discretized histogram over the torus.

3. **Correlation measure.** A scalar `I(A:B)` that is zero for a product
   state and positive for any correlation. Candidates: mutual information
   from the phase-space distribution; logarithmic negativity; a Bell-type
   correlator.

4. **Coarse-graining rule.** A map from `(theta_A, theta_B)` to a
   two-level outcome. The natural choice: threshold the phase difference
   at π/2. Then the joint distribution over binary outcomes is the input
   to a CHSH inequality.

None of these is present. The point of naming them is that they are small
and well-defined. The hypothesis is not vague; it is merely untested.

## 3. The test

The CHSH inequality is a necessary condition for quantum-like
correlation. Classical shared-prefix structure produces CHSH values
bounded by 2. Quantum-entangled subsystems violate the bound, with a
maximum of 2√2 ≈ 2.828 for the singlet state.

The test:

1. Drive the field to LOCKED, MIXED, and EXPLORING regimes.
2. At each regime, sample `n_samples` phase configurations.
3. For each configuration, apply the partition, coarse-grain to binary
   outcomes, and estimate the CHSH value.
4. Report the CHSH value per regime.

**Interpretation rules, fixed in advance:**

| Outcome | Reading |
|---|---|
| LOCKED CHSH > 2 | Substrate correlations can look quantum under this coarse-grain. Evidence for the emergence reading. |
| LOCKED CHSH ≤ 2, all regimes | Classical phase field. Any "quantum" third head is an external interpreter, not an emergent property. |

The second outcome is not a failure. It is the honest answer, and it
would fix the boundary between RES-308's quantum-shaped mathematics and
RES-501's quantum capability at the substrate level.

## 4. What this would change

If LOCKED CHSH > 2 under a fixed seed:

- The entanglement reading of the hierarchy pipeline becomes a live
  research direction. The next step is a persistent-tree implementation
  (`PersistentHierarchy` with structural sharing) so that the shared
  prefix structure is explicitly represented, not incidental.
- RES-308's `quantum_capability: False` posture is unchanged in the
  source, but the *substrate's* quantum-shaped claim gains a specific
  measured basis. This is not the same as quantum capability; it is a
  stronger statement than "quantum-shaped math" and a weaker one than
  "quantum".

If LOCKED CHSH ≤ 2:

- The entanglement reading is falsified at the substrate level. The
  pipeline's shared-prefix structure is a classical tree, and any
  quantum third head must be an external consumer, not an emergent
  property. This would be the correct place to stop pursuing the
  entanglement pipeline engine as a substrate claim.

## 5. Non-claims

- No entanglement claim. The word is used as a hypothesis to be tested,
  not a property asserted of the current system.
- No quantum speedup claim. Even under the strong outcome, no
  computational advantage is claimed. The CHSH test measures correlation
  structure, not compute.
- No replacement of RES-308. The constructive head remains the
  implemented third head. This document is a research direction; it does
  not supersede RES-308 or propose a different implementation of the
  same interface.
- No claim that the current hierarchy implementation has structural
  sharing. It does not. Two streams with a shared prefix re-derive the
  shared packets independently. The shared-prefix structure is a property
  of the *sequence of emitted packets*, not a memory optimization in the
  current code.
- No claim about the physical reality of the oscillator field. The field
  is a classical phase dynamical system. Whether its correlations admit a
  quantum reading is the question, not the assumption.

## 6. Open questions

- **Which partition?** The choice of `(theta_A, theta_B)` is not unique.
  Phase-adjacent, phase-opposite, and spectral partitions give different
  correlation measures. The first scan should fix one scheme and report
  sensitivity to alternatives.
- **Which measure?** Mutual information from a coarse-grained phase
  histogram is cheap but loses structure. Logarithmic negativity requires
  a density-matrix formulation that is not obvious for a phase field.
  The CHSH estimate is the first test because it is the most falsifiable
  and the least model-dependent.
- **What counts as "quantum" here?** The CHSH bound is a necessary
  condition, not sufficient. A field could exceed 2 by a classical
  mechanism that is not shared-prefix structure. The test reports the
  value; interpreting it as entanglement requires an additional
  assumption about what non-shared-prefix classical correlations can
  produce. That assumption should be stated explicitly in the results
  document before any claim is made.
- **If the test passes, what is the next discriminator?** The CHSH scan
  is a first check. A monotonicity test (does CHSH grow with r?) and an
  r-invariance test (does CHSH depend on the number of oscillators?)
  would refine the picture.

## 7. Implementation sketch

If the test is built, the module is
`src/resileos/substrate/entanglement.py`:

    partition(theta, scheme="adjacent") -> (theta_A, theta_B)
    mutual_information(theta_A, theta_B, bins) -> float
    chsh_estimate(field, partition_fn, n_samples) -> float

The driver is `scripts/run_chsh_scan.py`:

    drive field to LOCKED / MIXED / EXPLORING
    report CHSH in each regime

The results document is `docs/300-substrate/entanglement-results.md`. It
does not exist. It is where the boundary between quantum-shaped
mathematics and quantum capability would be located, empirically, for the
specific case of the oscillator field.

## 8. Read next

- [Constructive Head](constructive-head.md) — RES-308
- [Phasor Graph](phasor-graph.md) — RES-306
- [Hierarchical Encoding](../310-hierarchy/hierarchical-encoding.md) — RES-310
- [Streaming Substrate State](../310-hierarchy/streaming-state.md) — RES-311
- [Layered Mask Stack](../310-hierarchy/mask-stack.md) — RES-312
