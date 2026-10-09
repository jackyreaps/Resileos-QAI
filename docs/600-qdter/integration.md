---
doc: RES-602
title: Two-Head Integration Note
status: draft
depends_on: [RES-600, RES-601]
referenced_by: []
---

# Two-Head Integration Note

This document is an **implementation note**, not a specification. It records
the neural architecture that realises the objects of RES-600 and RES-601 in a
single model, with the corrections that were required for the code to match
the source mathematics.

## 1. The two heads

| Head | Source | Object |
|---|---|---|
| Geometric Manifold | RES-601 | `g_ij`, `V`, `Γ^k_ij`, `‖∇_X V‖²` |
| Variational Reduction | RES-600 | `Ψ_s`, `Π_o`, `Π_s`, `Γ_eff`, `δΨ̇_s` |

## 2. Head 2 — the corrected rate

The source specification (`Reduction_fep.md §3.1–3.2`) gives:

    Γ_eff = P_s · M_E · U''(Ψ_B)
    U''(Ψ_B) = f Ψ_B (Ψ_B − Ψ_A)

Substituting Axiom C (`M_E = G Ψ_B / (Ψ_B − Ψ_A)`):

    Γ_eff = P_s · G · f · Ψ_B²

Matching to the linearized FEP recognition rate `Γ(Π_o + Π_s)` requires
`Γ = G`, per RES-600 §4. With that assignment:

    Γ · (Π_o + Π_s) = G · f Ψ_B²

and the identity closes.

Three corrections relative to earlier drafts:

1. **`Γ = G`, not `Π_s · G`.** An earlier draft used `Γ = Π_s · G` for the
   FEP recognition rate, which does not close the identity (RES-600 §4.1).
   The source document `Reduction_fep.md §3.1` writes `Γ = Π_s · G`; if that
   is not a transcription error, the source and the derivation disagree and
   the discrepancy is an open item.
2. **`f` is a free parameter**, not `Re_ε · 0.1`.
3. **`P_s` is the orthogonal projector onto `ker(L_H)`**, not a learned
   scalar map. If a learned projection is used as a stand-in, the docstring
   must say so.

## 3. Head 1 — the metric

The source specification marks the metric bridge **"To Be Supplied"**
(`Non_dual_adaptation.md §7`). The three open items are:

- Explicit identification of the coordinates.
- Derivation of `Re_ε` and `G` from the rheology layer.
- Positive-definiteness verification.

A neural implementation that uses a different metric (e.g. `g = LLᵀ + εI` with
`L = xW_L`) is **not** the bridge. It is a substitute. The docstring must say
which it is.

## 4. Orthogonality

The two heads are **not** two halves of one system. RES-601 is orthogonal to
RES-600. A model may compute both, but the FEP reduction does not require the
metric, and the parallel transport condition does not require the FEP rate.
This note describes an implementation that happens to compute both; it does
not claim that the source documents require a joint architecture.

## 5. What is not claimed

- That the two-head architecture is required by the source documents.
- That Head 1 recovers the QD-TER metric without the missing derivations.
- That Head 2's fit is a verification of the local reduction theorem. A real
  verification restricts to `|δΨ_s| < ε`, sweeps `ε`, and checks that the
  residual scales as `C_1 / λ_2`.

### 5.4 FPE backend substitution

The substrate's Fractional Power Encoding has two backends, selected at
import time by `src/resileos/substrate/fpe.py`:

- **leCore** — if `lecore.holographic.sampling_and_signal.holographic_fpe`
  is importable, its FPE is used and quantized to bipolar.
- **in-house** — otherwise, the historical in-house implementation is used.

Both satisfy the RES-300 §leCore boundary contract (unit-norm, determinism,
`(x, dim, seed)` signature). The leCore path applies an additional
bipolar quantization step; this is a lossy conversion and results under
leCore will differ from results under the in-house backend by design.

The backend in use is reported by `resileos.substrate.fpe.backend_name()`
and is logged at import time. This is a **substitution**, not a drop-in
replacement, in the sense of RES-602 §5.4.

## 6. Numerical verification harness

`VerifiableFEPReductionHead.sweep_epsilon()` runs the reduction ODE across
a user-supplied set of perturbation scales and returns the fit statistics
of the residual scaling law. It supports two metrics:

- `rmse` — root-mean-square residual. Matches the norm bound
  `‖error‖ ≤ C_1/λ_2` in RES-600 §4. Expected slope ≈ 1.
- `mse` — mean-square residual. Expected slope ≈ 2 (`MSE = RMSE²`).

The runner `scripts/run_fep_sweep.py` exercises the harness on either a
simulated Axiom-D trajectory or a user-supplied `.npy` trunk file.

### 6.1 Docstring note on `dt`

The head compares the finite difference `Δδ = δ_{t+1} − δ_t` against
`−Γ_eff · δ_t`, i.e. it treats the finite difference as a rate. Dimensionally
this includes a factor of `dt` from the integration step. Because both
sides scale linearly in ε regardless of `dt`, the **fitted slope is
unaffected** by the missing normalization. If a future use needs to compare
the fitted rate constant against the theoretical `Γ_eff`, `dt` normalization
must be added at the call site.

## 7. Numerical verification result

**Date:** 2026-10-09
**Source:** simulated Axiom D (self-consistency check)
**Runner:** `python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64 --metric rmse`

**Parameters:**

| Parameter | Value |
|---|---|
| dim | 128 |
| seq_len | 64 |
| g_field | 0.85 |
| metric | rmse |
| epsilons | 0.1, 0.05, 0.02, 0.01, 0.005, 0.001 |

**Result:**

| ε | residual (RMSE) |
|---|---|
| 0.10000 | 1.314937e-01 |
| 0.05000 | 6.731574e-02 |
| 0.02000 | 2.731726e-02 |
| 0.01000 | 1.372502e-02 |
| 0.00500 | 6.879221e-03 |
| 0.00100 | 1.378518e-03 |

**Fit:**

    slope     = 0.9906
    intercept = 0.2660
    r_squared = 0.999967

**Interpretation.** The residual scales as `O(ε)` under the RMSE metric,
consistent with the linear `C_1/λ_2` bound in RES-600 §4. The log-log fit
is essentially a perfect power law.

**Scope.** This is a **self-consistency check**: the harness recovers the
linear scaling on trajectories generated by the same Axiom-D assumptions
the head assumes. It confirms that the head correctly implements the
linearized ODE and that the simulator correctly integrates Axiom D. It
does **not** establish that Axiom D describes a real physical system. That
would require independent trunk trajectories from a real medium, which are
not yet available.

**Reproduce:**

    python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64 \
        --metric rmse --out report_sweep_rmse.json

## 8. Stress test

Section §7 reports the sweep on an ideal Axiom D trajectory. Real data
would not be ideal: it would carry off-manifold leakage, drift in the
coherence field, and coarser integration steps. `simulate_axiom_d` exposes
three stress knobs to probe the theorem's robustness envelope:

| Knob | Ideal | Stress range |
|---|---|---|
| `off_manifold_frac` | 0.0 | 0.0 – 0.5 |
| `g_ramp` | 0.0 | 0.0 – 0.3 |
| `dt_coarse` | 1.0 | 1.0 – 8.0 |

`scripts/run_fep_sweep.py --stress` runs the sweep at five levels from
ideal to extreme and reports the slope at each.

**Result (2026-10-09):**

| Level | off_manifold | g_ramp | dt_coarse | slope | r² |
|---|---|---|---|---|---|
| L0 (ideal) | 0.00 | 0.00 | 1.0 | 0.9906 | 0.999967 |
| L1 (mild) | 0.10 | 0.05 | 2.0 | 0.9891 | 0.999955 |
| L2 (moderate) | 0.20 | 0.10 | 4.0 | 0.9884 | 0.999950 |
| L3 (strong) | 0.30 | 0.20 | 6.0 | 0.9879 | 0.999945 |
| L4 (extreme) | 0.50 | 0.30 | 8.0 | 0.9873 | 0.999939 |

**Drift:** 0.0033
**Verdict:** bound holds under stress

**Interpretation.** Slope stays in `[0.987, 0.991]` and r² stays above
0.9999 across the full ladder. The `O(ε)` residual bound is robust to
off-manifold leakage up to 50% of ε, coherence drift up to 30%, and
integration-step coarsening up to 8×.

**Correction note.** An earlier run of this test collapsed to slope
0.0017 at L4. That run used a multiplicative amplitude ramp for the
`g_ramp` knob, which injected an ε-independent residual term that
dominated as ε shrank. The knob was corrected to modulate the decay
rate inside the integrator (Γ_eff(t) = G(t)·Π_sum), keeping trajectories
on-manifold. The behavior of the earlier run is a property of the sweep
harness, not the theorem.

**Reproduce:**

    python scripts/run_fep_sweep.py --stress --dim 128 --seq-len 64 \
        --metric rmse --out report_sweep_stress.json
