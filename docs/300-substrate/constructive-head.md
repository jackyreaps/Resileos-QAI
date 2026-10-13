---
doc: RES-308
title: Constructive Head
status: proposal
depends_on: [RES-200, RES-201, RES-306]
referenced_by: []
---

# Constructive Head

A third head for the substrate that produces a drift **direction** from
the core's own dynamics, without training and without a target vector.

## 0. Quantum, precisely

**Quantum capability.** Physical superposition, entanglement,
measurement, error-corrected gates. Requires a QPU. RES-501 territory:
speculative, downstream, absent from this repository.

**Quantum-shaped mathematics.** Complex numbers, unit-modulus phasors,
unitary operators, Hermitian matrices. Runs on classical CPUs.
Deterministic. Used throughout the substrate.

**The quantum condition, not enforced.** Remove every occurrence of
"quantum" from the source and the operations are unchanged.

The constructive head is quantum-shaped mathematics.
`ConstructiveHead.describe()` returns
`{"quantum_capability": False, "quantum_shaped_math": True}`.

### 0.1 Design continuity with QD-TER-Human-Medium

The oscillating and coupled-oscillator language traces to the sibling
repository:

- **Kuramoto coupling form.** `QD-TER Human-Medium v5.0` §3 defines the
  global chiral commutator:
  `Σ_{i,j} κ_ij sin(φ_i − φ_j − χ_ij · Δψ_ij) = 0`.
  Same functional form as the Kuramoto coupling in
  `src/manifold/EEG_hyperscan.py::_coupled_oscillator`. The form is
  standard Kuramoto.
- **Seven-engine manifold.** v5.0 §2 lists seven brain-region
  oscillators. These map conceptually to the substrate's rank-`r`
  latent oscillators (default `r = 8`). The mapping is a scale
  argument, not a state-space extension. The engines run at 1–30 Hz;
  the substrate θ evolves per query. The temporal scales differ and
  the correspondence is structural, not physical.
- **Falsification protocols.** v5.0 §11 lists 38 experiments. None of
  them applies to the substrate directly; they are the sibling
  repository's own tests.

The constructive head does **not** use Kuramoto coupling. It is a
static constructive operator. A future oscillator-dynamics head
(§5 below) would instantiate the Kuramoto form at the substrate scale.

## 1. Why a third head

Two heads already exist:

| Head | Reads | Produces | Doc |
|---|---|---|---|
| Geometry | `Ub`, `Vb` | metric penalty + `V_seq` | RES-601 |
| Reduction | `Λ`, monitors | slow coordinate + ODE error | RES-600 |

Neither produces a direction vector in ambient space. The drift in
`HDRIFTAdapter` is a scalar multiple of `x_enc`, which has no
directional content.

The constructive head fills that gap using only quantities the core
already emits. It does not modify the packet (RES-201 frozen).

## 2. Two mechanisms

### 2.1 Trend

    direction_trend = Vb @ (Λ_t − Λ_{t−1}) @ Ub

The finite difference `Λ_t − Λ_{t−1}` is the scar's first-order motion.
Lifting it through `Vb` and `Ub` returns it to the ambient block shape
`(m, n)`, flattened and zero-padded to `dim`.

Requires `Λ_{t−1}`. On the first step, returns zero.

### 2.2 Phase

    J = diag(exp(i·θ)) + strict_lower(Λ)
    direction_phase = Re(Ub @ J @ Vb) − Ub @ Vb

The phase vector θ acts as a complex rotation on the latent axis of
`Ub` and `Vb`. Requires θ. When θ is `None`, returns zero.

## 3. Combination

Modes: `"trend"`, `"phase"`, `"both"`. `"both"` is additive. No
learned weights.

## 4. What is not claimed

- **Predictive accuracy.** Whether `x_t + direction` is closer to
  `x_{t+1}` than `x_t` is an empirical question. No `(x_t, x_{t+1})`
  dataset exists in this repository.
- **Quantum capability.** See §0.
- **Training.** Parameter-free.

## 5. Candidate: oscillator dynamics for θ

A future head could replace the current θ dynamics (a zero-sum vector
updated from monitors) with a Kuramoto-coupled system. Design
resolutions:

1. **N = r oscillators.** The substrate's rank `r` (default 8). v5.0
   §2 uses seven brain-region engines; the substrate uses eight latent
   oscillators. The numbers are close by design continuity, but the
   mapping is a scale argument.

2. **W = PhasorGraph adjacency.** The coupling matrix is the topology
   of the semantic graph. Phase alignment becomes a function of the
   facts and relations.

3. **Coupling sign.** Option A:
   `dθ_i/dt = ω_i + κ/(α+ε) Σ_j W_ij sin(θ_j − θ_i)`.
   High coupling at low error, convergence. Matches the substrate's
   existing behavior (`Titanos._ask` converges when confident, explores
   when uncertain).

   Option B (`κ·ε`) is the basal-ganglia regime from v5.0 §2.5 —
   stress clamps the system into a rigid state. Different behavior;
   not the current substrate's.

   **Default for the substrate: Option A.**

4. **Resonance.** Golden-ratio frequency spacing reduces the density
   of near-resonances; it does not eliminate them. v5.0 §5 uses
   sub-harmonic integers `{10³, 10⁶, 10⁹}` in the temporal bridge.
   The `ω_i = φⁱ mod Ω_base` ladder is an addition, not a v5.0
   citation.

### 5.1 Status

Candidate. The three questions above are answered. What remains before
implementation:

- A sequence dataset with real `(x_t, x_{t+1})` pairs, or a decision
  that the coupling will be tested on the synthetic 64-dim blocks.
- A decision on whether to replace the current θ dynamics or add a
  parallel oscillator head.
- A written acceptance test: what does the Kuramoto θ predict that the
  current zero-sum θ does not, and how is that measured?

## 6. Interface

    ConstructiveHead(dim, m, n, mode="trend", scale=1.0)
    forward(x_enc, packet, lambda_prev=None, theta=None) -> np.ndarray

Returns `(dim,)` real. Zero when the inputs for the active mode are
`None`.

## 7. Read next

- [Classical Core](../200-core/classical-core.md) — RES-200
- [Control Packet](../200-core/control-packet.md) — RES-201
- [Phasor Graph](phasor-graph.md) — RES-306
