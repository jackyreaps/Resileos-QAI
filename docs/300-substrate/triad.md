doc: RES-304
title: Structure-Flux-Mode Triad
status: draft
depends_on: [RES-200, RES-300, RES-302]
referenced_by: [RES-318]

# Structure-Flux-Mode Triad

The residual core already implements three stages: a constraint
structure, a flux that moves through it, and a discrete mode that
emerges. This document names those stages, points at the code that
realizes them, and defines the experiment that would show whether the
triad produces good basins on a target problem.

It does **not** claim that any problem's complexity class changes. It
does **not** claim a speedup over any specific baseline. It claims that
basin structure is a measurable property of the system and should be
measured before any stronger claim is made.

## 1. The three stages

| Stage | What it is | Where it lives |
|---|---|---|
| **Structure** | The constraint graph. What states are reachable and how they couple. | `src/resileos/core.py` — strictly-lower `Λ`; `src/resileos/packet.py` — schema fields |
| **Flux** | The flow that moves the state through the structure. | `src/resileos/adapter.py` — `holographic_drift`; `src/resileos/core.py` — `_scar_update`; `src/resileos/substrate/reduction.py` — Axiom D `F(Ψ, f)` |
| **Mode selection** | The discrete outcome among attractors. | `src/resileos/substrate/reduction.py` — wells `φ_A`, `φ_B`; `src/resileos/core.py` — Prime-Tower rank; `src/resileos/sigma.py` — sigma gate regime switch; `src/resileos/abstention.py` — parity `μ` |

The stages are not a new abstraction. They are a description of what the
existing code does. §9 extends this to the multi-engine case, where the
stages become constructive rather than descriptive.

## 2. Basin metrics

Four quantities characterize a mode-selection landscape. Each is
measurable on any instance.

| Metric | Definition | What it tells you |
|---|---|---|
| **Basin volume** | Fraction of initial states that converge to a target mode | Reachability — how easy the target is to find |
| **Basin depth** | Maximum perturbation magnitude that leaves the mode intact | Robustness — how much noise the mode tolerates |
| **Boundary dimension** | Fractal dimension of the basin boundary | Whether the landscape is "easy" (smooth boundary) or "hard" (fractal) |
| **Hopping rate** | Frequency of flux crossings from one basin to another | Whether the system explores or settles |

A good landscape has high volume, high depth, low boundary dimension,
and low hopping rate. A bad landscape has the opposite.

`src/resileos/substrate/basin.py` implements all four, plus
`boundary_codim` and `basin_entropy`. Every function takes a `step_fn`
and a `target_mode`; none is specific to a single `ResidualCore`. §9
relies on this.

## 3. Target problem

**Primary: MaxCut.**

- NP-hard in the worst case.
- Natural energy landscape: `H = -Σ_{(i,j) ∈ E} J_ij · s_i · s_j` with `s_i ∈ {-1, +1}`.
- Matches the cubic structure of Axiom D's `F(Ψ, f)` after the standard Ising transformation.
- Small instances (n ≤ 30) exactly solvable by brute force.
- Well-studied baselines: Goemans–Williamson (SDP relaxation), QAOA, simulated annealing, Tabu search.

**Fallback: TSP.** Euclidean instances, 20–40 cities. Exact via
Held–Karp up to ~25; beyond that, nearest-neighbor + 2-opt as baseline.

## 4. The scaling check

Three sizes. For each, run `K` random initializations (default `K = 200`)
and record basin volume to the best-known-or-exact mode.

| Size | `n` | Method to find ground truth |
|---|---|---|
| Small | 10 | brute force |
| Medium | 20 | brute force (MaxCut) or Held–Karp (TSP) |
| Large | 30 | best of 1000 restarts of baseline + SDP bound |

Fit basin volume vs `n`. Three cases:

- **Volume flat in `n`** — reachability is scale-invariant. Strong result.
- **Volume decays like `1/poly(n)`** — polynomial advantage over random search. Real result.
- **Volume decays like `exp(-cn)`** — same as any local landscape. No new claim.

The third case is not a failure. It is the honest answer to a
falsifiable question. Report it either way.

## 5. Baselines (for context only)

Basin volume should be compared against:

- **Random search** — uniform sampling, keep the best.
- **Local search** — greedy bit-flip (MaxCut) or 2-opt (TSP).
- **Simulated annealing** — standard schedule, same budget.

If the triad's basin volume beats all three at equal budget, that is the
result. If it beats only random search, that is also the result. The
comparison does not need to include Goemans–Williamson or QAOA. Those
are separate classes of method with different time budgets. The three
baselines above are the honest floor.

## 6. What would falsify the strong claim

The strong claim is: *the triad produces good basins on structured
NP-hard instances, and this good behaviour scales.*

Falsified if:

1. Basin volume decays exponentially with `n` on every structured class attempted.
2. The observed mode selection is indistinguishable from local search with the same energy landscape.
3. Solutions found are optimal only for instances that were already easy by a trivial bound.
4. Scaling past `n = 30` shows no improvement over `n = 20`, then no improvement over `n = 10` — a flat wall.

Any of these is a valid outcome. The document's purpose is to make them
reportable.

## 7. What this is not

- **Not a claim about complexity classes.** Cook–Levin is not affected by any dynamical framing.
- **Not a claim of quantum speedup.** The quantum band in this repo is labelled `QUANTUM_SIM`. RES-501 still gates any quantum claim behind experimental characterization.
- **Not a claim about the token path.** The triad describes the classical memory layer. Text modeling is a separate track (RES-502).
- **Not a claim about the bridge.** RES-601 §7 remains locked; the candidate in RES-606 is a conformal substitute.

## 8. Deliverable

A short report at `docs/300-substrate/triad-results.md`, containing:

- Instance generator and seed list
- Basin volume, depth, boundary dimension, hopping rate per size
- Scaling fit and confidence interval
- Baseline comparison table
- Verdict: one of §4's three cases

Nothing in this document requires the phase-weighted graph, the carrier
bands, the Lean proofs, or any of the downstream design proposals.
Those are all separate. This is the minimum experiment that could
justify them.

## 9. Multi-engine extension

§1 describes a single `ResidualCore`. RES-318 (`engine-group.md`)
composes N cores into an `EngineGroup` with a shared `CouplingField`.
At that level the triad shifts from *descriptive* to *constructive*:
the three stages are chosen by the coupling design rather than observed
in one core's code.

The mapping and the metric reuse are specified in RES-318 §3. Two
consequences for this document:

- **The four metrics in §2 apply unchanged.** `basin.py` takes a
  `step_fn`; a group step function is a valid input. No new metric is
  needed to measure group-level basins.
- **The scaling check in §4 becomes a check against N.** The three
  cases (flat / `1/poly` / `exp`) apply with `n → N`. The third case is
  still not a failure.

RES-318 §11 raises the load-bearing question this section defers:
*is a group-level triad actually a triad, or does the coupled system
have only a continuous phase distribution with no discrete modes?* If
there are no discrete group modes, the third stage does not exist at
group level and the triad reduces to Structure + Flux. That is an
empirical question, answered by RES-318 §8 invariant 5.

This document does not change. §9 is a pointer, not a rewrite.

## 10. Read next

- [Engine Group Composition](engine-group.md) — RES-318
- [SDM + Hopfield Attractor Memory](sdm-hopfield.md) — RES-317
- [Classical Core](../200-core/classical-core.md) — RES-200
- [HDRIFT Adapter](hdrift-adapter.md) — RES-300
- [Abstention](abstention.md) — RES-302
- [Documentation Index](../readme.md)
