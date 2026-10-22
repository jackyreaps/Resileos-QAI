doc: RES-318
title: Engine Group Composition
status: draft
depends_on: [RES-200, RES-201, RES-304, RES-306, RES-310, RES-311, RES-317]
referenced_by: []

# Engine Group Composition

A single `ResidualCore` produces a single stream of packets. The
framework-native objective (recovery, coherence, residue) was designed
for *correlated* multi-stream state: N engines whose monitors are partly
driven by their relation to each other, not just by their own dynamics.

This document specifies the composition layer that produces that state.
It is interfaces only. It defines what must exist for the framework-
native objective to have a non-degenerate training signal.

It does not implement the composition and does not re-open any training
question. The single-engine `k = 0.9` measurement is a measurement of a
degenerate configuration; this document is the prerequisite for
measuring the non-degenerate one.

## 0. Status

Draft. No implementation exists. First `N = 3` engines. Scale to `N = 8`
is the sector-bus-aligned target (RES-312) and is deferred until `N = 3`
is verified.

## 1. Why single-engine is degenerate

Three aux losses were trained against a single `ResidualCore`:

| Loss | Target | Why it was degenerate |
|---|---|---|
| recovery | `lat_s_k` projection | The packet's own latent; no cross-stream structure to recover |
| coherence | phase agreement | A single field's internal R; already maximized by Kuramoto |
| residue | history of `ΔS`, `F_res` | One stream; no correlation to exploit |

None of these can show efficiency gains because none has anything to
correlate *against*. The objective is not wrong; the substrate was too
small for it to have signal.

## 2. Composition

    EngineGroup
      ├── ResidualCore_0   (seed 0)
      ├── ResidualCore_1   (seed 1)
      ├── ResidualCore_2   (seed 2)
      └── CouplingField    (shared phase lattice, N oscillators)

Each engine has its own `CoreConfig`, its own `r`-rank state, its own
packet stream. The `CouplingField` holds one phase per engine and steps
them together. The coupling is what makes the streams correlated.

N is a constructor argument. `N = 3` is the first target. N is fixed at
construction; engines are not added or removed after `__init__`.

## 3. Triad correspondence

RES-304 defines the Structure-Flux-Mode triad as a *description* of what
a single `ResidualCore` already does. §1 of that document is explicit:
"the stages are not a new abstraction. They are a description of what
the existing code does."

At group level that changes. The coupling matrix, the drive rule, and
the per-engine cross terms are **design decisions**, not inherited
behaviour. The triad shifts from *descriptive* (one engine) to
*constructive* (N engines): the same three stages, but chosen rather
than observed.

### 3.1 Stage mapping

| Triad stage (RES-304 §1) | Single-engine realization | Group-level realization |
|---|---|---|
| **Structure** | strictly-lower `Λ` in `core.py`; `packet.py` schema | `CouplingField.W` (N×N) plus each engine's own `Λ` |
| **Flux** | `holographic_drift`; `_scar_update`; Axiom D `F(Ψ, f)` | phase differences driving each engine's `F_res`, `ΔS`, `μ` (§5) |
| **Mode selection** | wells `φ_A`/`φ_B`; Prime-Tower rank; sigma gate; parity `μ` | the joint attractor the coupled N-engine system settles into |

The third row is the one that needs work. In the single-engine case,
`φ_A`/`φ_B` are two wells in `reduction.py`. At group level the
attractor is a *joint* state across N engines — and whether that joint
state is discrete at all is an open question (§11).

### 3.2 Basin metrics are already the acceptance test

RES-304 §2 defines four metrics: basin volume, depth, boundary
dimension, hopping rate. `src/resileos/substrate/basin.py` implements
all four plus `boundary_codim` and `basin_entropy`. Every one of those
functions takes a `step_fn` and a `target_mode`. They do not care
whether the step function wraps one core or a coupled group.

That means the group-level landscape is measurable **without writing a
new metric**. The `step_fn` is "advance the group one step and return
the joint mode." Everything downstream — volume, depth, boundary
dimension, hopping, codimension, entropy — works unchanged.

### 3.3 The scaling check maps n → N

RES-304 §4 fits basin volume against problem size `n` and classifies
the result into three cases. At group level the independent variable
becomes engine count `N`:

| Triad §4 case (per `n`) | EngineGroup analogue (per `N`) |
|---|---|
| Volume flat in `n` | Group basin volume flat in N — coupling produces scale-invariant reachability |
| Volume ~ `1/poly(n)` | Group basin volume ~ `1/poly(N)` — polynomial advantage over uncoupled engines |
| Volume ~ `exp(−cn)` | Group basin volume ~ `exp(−cN)` — no emergent group structure |

The third case is **not a failure** in RES-304 §4 ("It is the honest
answer to a falsifiable question. Report it either way."). The same
applies here: exponential decay in N means the coupling does not
produce good group-level basins, and that is a reportable result.

### 3.4 Sheath at group level

`basin_boundary_dim` and `boundary_codim` already report the
mask→sheath regime change that RES-312 documents for the mask stack.
The same transition can occur at the *engine* level: with high N and
strong coupling, the group-level boundary saturates into a membrane.
That is a second place to observe the regime change, using the same
metrics, with no new code.

### 3.5 What the group adds to SDM/Hopfield

RES-317 (SDM + Hopfield Attractor Memory) cleans up crosstalk between
VSA unbinding and codex lookup. It operates on whatever vector it is
given. With an `EngineGroup`, the vector it is given can be the *group*
state rather than a single-engine state — which is a wider address space
and a richer attractor landscape. Without the group, SDM has no group
state to clean.

## 4. CouplingField

A new type. It does not extend `KuramotoField`; that class couples the
`r` oscillators *within* one engine and its contract is stable.

    class CouplingField:
        """N-engine phase lattice. One phase per engine."""

        def __init__(
            self,
            n_engines: int,
            kappa: float = 1.0,          # cross-engine coupling strength
            alpha: float = 0.5,
            dt: float = 0.1,
            seed: int = 0,
        ) -> None: ...

        @property
        def theta(self) -> np.ndarray:
            """(n_engines,) current phase per engine."""

        def step(
            self,
            drives: np.ndarray,          # (n_engines,) per-engine drive
            W: np.ndarray | None = None, # (N, N) coupling weights
        ) -> None:
            """Advance one step. W defaults to all-ones minus identity."""

        def order_parameter(self) -> float:
            """R over the N engine phases."""

        def phase_difference(self, i: int, j: int) -> float:
            """Signed phase difference theta_i - theta_j, wrapped to (-pi, pi]."""

Coupling topology: all-to-all by default. With `N = 3`, that is three
pairwise terms. `W` may be set to zero on specific pairs to test
directional or sparse coupling, but the default is fully connected.

The `CouplingField` does not know about residual cores, packets, or
monitors. It holds phases and steps them. Everything else is the
`EngineGroup`'s concern.

## 5. Drive rule

Each engine's monitors are computed as today (`core.monitors()`) plus
two cross terms:

    F_res_i  = F_res_i_own  + β_F · Σ_{j≠i} |phase_difference(i, j)| / (N-1)
    DeltaS_i = DeltaS_i_own + β_S · (1 - cos(phase_difference(i, j̄)))
    mu_i     = mu_i_own  XOR  (phase_difference(i, j̄) < 0)

where `j̄` is the engine with the largest phase difference from `i`.

`β_F` and `β_S` are config parameters, default `0.1` and `0.1`. They
control how much cross-engine state enters each engine's own drive. At
`β = 0` the engines are uncoupled and the group reduces to N independent
single-engine runs. At `β = 1` the cross terms dominate and the engines
synchronize to the coupling field.

The `μ` XOR is deliberate: parity is the engine's own signal, and the
phase-difference sign is the cross term. XOR is the minimal way to
encode "engine says A, coupling says B" as a single parity flip. The
exact form is a design choice; `β_F` and `β_S` are tunable.

## 6. Coupled packet

A new type. It wraps N single-engine packets and the coupling state at
the moment they were emitted.

    @dataclass
    class CoupledPacket:
        packets: tuple[HierarchicalPacket, ...]   # length N
        phases: tuple[float, ...]                 # length N
        R_shared: float                           # CouplingField.order_parameter()
        coupling_matrix: np.ndarray               # (N, N) phase differences
        residue_history: tuple[np.ndarray, ...]   # length N, per-engine ΔS trace

Each underlying packet is a standard `HierarchicalPacket` from RES-310.
The `CoupledPacket` adds the cross-engine fields; nothing in the
single-engine packet format changes.

`coupling_matrix[i,j]` is `phase_difference(i, j)` at emission time.
The diagonal is zero. The matrix is antisymmetric.

`residue_history[i]` is the last `K` values of `ΔS` for engine `i`,
where `K` is a config parameter (default 8).

## 7. Data generator

The training data for the framework-native objective is a stream of
`CoupledPacket`. The generator's interface:

    class CoupledStreamGenerator:
        """Emits coupled packets from N engines stepping in lockstep."""

        def __init__(
            self,
            group: EngineGroup,
            drive_source,          # callable: (t) -> (N,) drive vector
            seq_len: int = 64,
        ) -> None: ...

        def __iter__(self) -> Iterator[CoupledPacket]:
            """Yield packets indefinitely. Each step advances all N engines
            and the coupling field together."""

        def reset(self) -> None: ...

The `drive_source` is what makes the streams differ. In a synthetic
setup it might be white noise plus a slow drift. In a real setup it
would be the residual stream from an actual data source, split N ways.

The generator is deterministic given a seed. Two generators with the
same seed and the same `drive_source` produce identical streams.

## 8. Invariants

What must hold for the composition to be useful:

1. **Phase differences are informative.** If `phase_difference(i, j)` is
   always near zero, the engines are synchronized and there is no
   cross-stream structure. At `β = 0.1`, R over the coupling field
   should be in `(0.2, 0.8)` — not locked, not scattered.

2. **Monitors are correlated but not identical.** `F_res_i` and
   `F_res_j` should have nonzero Pearson correlation across the stream
   (target `0.2 < ρ < 0.8`). At `ρ = 1` the engines are redundant; at
   `ρ = 0` they are independent and there is nothing to learn.

3. **Residue histories diverge.** `residue_history[i]` and
   `residue_history[j]` should be distinguishable. If they are
   identical, the XOR parity and the `DeltaS` cross term are both
   degenerate.

4. **The coupling field converges.** If `kappa > 0`, the coupling field
   should reach a stable orbit within `n_warm` steps. If it does not,
   `κ` is too high for the number of engines.

5. **Group basins are measurable.** With `step_fn` = "advance the group
   one step, return the joint mode," the four RES-304 §2 metrics must
   be computable using `basin.py` unchanged. If they are, the triad's
   scaling check runs against N (§3.3). If they are not — because the
   group does not settle into a mode — the coupling is too weak or the
   drive is too noisy, and no training measurement downstream will be
   meaningful.

These invariants are testable before any training happens. If any fails,
the training measurement will be degenerate for the same reason the
single-engine ablation was.

## 9. Non-claims

- Not a training implementation. No loss function, no training loop,
  no optimizer.
- Not a claim that the framework-native objective will show `k > 1` on
  this composition. It might, it might not. The composition is the
  prerequisite for asking, not the answer.
- Not a claim about scale. `N = 3` is a toy. `N = 8` is the next step.
  Neither is 1T-parameter scale.
- Not a replacement for `AgencyGroup` (RES-307). Agency is heuristic
  routing over registered handlers. `EngineGroup` is substrate
  composition. They are orthogonal.
- Not a change to `KuramotoField` or `ResidualCore`. Both keep their
  existing contracts. `CouplingField` is a new type that sits between
  the N engines.
- Not a redefinition of the triad. RES-304 remains the single-engine
  description. §3 here is the group-level extension, not a rewrite.

## 10. Implementation order

1. **`CouplingField`** — new module `src/resileos/substrate/coupling.py`.
   Testable in isolation (phases step, R behaves, phase differences are
   antisymmetric). No dependency on `ResidualCore`.
2. **`CoupledPacket`** — new type in the same module. Testable with
   synthetic packets. No dependency on `EngineGroup`.
3. **`EngineGroup`** — new module `src/resileos/substrate/engine_group.py`.
   Holds N cores, N streams, one coupling field. Steps them together.
   Emits `CoupledPacket`.
4. **`CoupledStreamGenerator`** — in the same module. Produces the
   training stream. Testable with a synthetic `drive_source`.
5. **Invariant tests** — §8 as test cases, including the group-level
   basin measurement via `basin.py` unchanged. Run before any training.
6. **Only then** — carrier training on `CoupledPacket`. The framework-
   native objective re-enters as a real question.

Steps 1–3 are the composition. Step 4 is the data path. Step 5 is the
gate. Step 6 is the question. Do not skip to 6.

## 11. Open questions

- **Is the group-level triad actually a triad?** The single-engine triad
  has well-defined `φ_A`/`φ_B` wells. The group-level analogue would be
  a joint mode across N engines. Whether the coupled system has discrete
  joint modes — or only a continuous phase distribution — is the
  load-bearing question. If there are no discrete group modes, the
  "mode selection" stage does not exist at group level, and the triad
  reduces to Structure + Flux with no third stage. The §8 invariant 5
  test answers this empirically.
- **Is coupling fundamentally different from a larger single engine?**
  A single `ResidualCore` with `r = 24` has as many latent dimensions as
  three cores with `r = 8`. Is cross-engine coupling fundamentally
  different from one larger core, or is it a computational trick for
  the same thing? The composition only matters if it is fundamentally
  different. Not answered here.
- **Coupling topology at N > 3.** All-to-all with N = 8 is 28 pairs.
  Does sparse coupling (grid, ring, or hub-and-spoke) preserve the
  correlation structure while reducing coupling cost? Not specified.
- **Drive source at real scale.** The synthetic `drive_source` is
  white noise plus drift. At real scale it would be the token embedding
  stream or the packet stream from a lower layer. The interface accepts
  either; the choice is deferred to the first real training run.
- **The `j̄` selection rule.** §5 uses "the engine with the largest
  phase difference from `i`". Is that the right choice? Alternatives:
  mean phase difference, or weighted by coupling matrix `W`. Not
  tested.
- **Residue window length.** `K = 8` is a placeholder. The right value
  depends on the timescale over which residue correlates across engines.
  Not measured.

## 12. Read next

- [Structure-Flux-Mode Triad](triad.md) — RES-304
- [SDM + Hopfield Attractor Memory](sdm-hopfield.md) — RES-317
- [Classical Core](../200-core/classical-core.md) — RES-200
- [Control Packet](../200-core/control-packet.md) — RES-201
- [Phasor Graph](phasor-graph.md) — RES-306
- [Hierarchical Encoding](../310-hierarchy/hierarchical-encoding.md) — RES-310
- [Streaming Substrate State](../310-hierarchy/streaming-state.md) — RES-311
- [Documentation Index](../readme.md)
