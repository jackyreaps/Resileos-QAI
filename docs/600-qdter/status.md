---
doc: RES-604
title: QD-TER Bridge Status
status: stable
depends_on: [RES-600, RES-601, RES-602, RES-603]
referenced_by: []
---

# QD-TER Bridge Status

Single-page inventory of the RES-600 series. Updated when an open item
closes. Each row points to the doc that owns it.

## Closed

| Item | Where | Evidence |
|---|---|---|
| FEP reduction algebra | RES-600 §3–§4 | derived; the Γ definition discrepancy is recorded as resolved in §4.1 |
| Numerical verification, ideal trajectory | RES-602 §7 | slope 0.9906, r² 0.999967 on simulated Axiom D |
| Numerical verification, stress ladder (RMSE) | RES-602 §8.1 | slope range 0.987–0.991, drift 0.0033 |
| Numerical verification, stress ladder (MSE) | RES-602 §8.2 | slope range 1.975–1.981, drift 0.0065 |
| SPD utility | RES-601 §7 item 3 | `src/resileos/substrate/spd.py` |
| Conformal placeholder metric | `spd.py` | labelled per RES-602 §5.4 |
| ε-sweep harness | `reduction.py` | `sweep_epsilon(metric="rmse"|"mse")` |
| ε-sweep API | `app.py` | `POST /api/v1/sweep_epsilon` (ungated) |
| ε-sweep UI | `ui.py` | tab in the Streamlit console |
| Bridge lock | `geometry.py` | `BridgeMetricHead` raises `NotImplementedError` with a message naming the open items |
| Rheology interface | `rheology.py` | `RheologyCoordinates` raises on every method, naming the missing input |
| leCore FPE substitution | RES-300 §leCore boundary | `substrate/fpe.py` selects backend at import; contract preserved |
| leCore HTTP client | RES-605 | `src/resileos/integration/lecore_client.py` |

## Open — canonical bridge (RES-601 §7)

These four items block unlocking `BridgeMetricHead`. They require
source material, not code.

### Item 1 — coordinate map x

**Blocker:** no explicit map from the rheology layer state to a
coordinate `x ∈ R^d` exists in-repo.

**What exists:** shell index, residual density, waist projector, fold
state. These are structural labels, not a coordinate parametrization.

**Interface:** `RheologyCoordinates.map_state_to_coordinates` in
`src/resileos/substrate/rheology.py`.

**Candidate:** RES-606 records a candidate form for `x` as a vector
`(j, r, s, n)`, with a scalar reduction `x_slow = normalize(j)` for
code. Not the canonical bridge.

### Item 2a — Re_ε(x) field

**Blocker:** global locks exist. The local velocity scale `|u(x)|`
required for `Re_ε(x) = |u| ℓ_res / ν_res` is not derived as a function
of `x`.

**Interface:** `RheologyCoordinates.re_epsilon`.

**Candidate:** RES-606 §2 gives `Re(x) = |F_res|(x) · τ / (k · L)` with
tunable parameters, plus a scale check noting the coefficient is ≈ 0.05
at defaults. Not the canonical derivation.

### Item 2b — G(x) field

**Blocker:** `G = √(OXTR · GJ)` is stated as a composition, but neither
factor is identified with a runtime monitor.

**Candidates in the substrate:** scar energy `‖Λ‖`, residual flux
`F_res`, sharpness `ΔS`. No source doc picks one.

**Interface:** `RheologyCoordinates.g_field`.

**Candidate:** RES-606 §3 uses the schedule form
`G(t) = g_0(1 + g_ramp · t/(T-1))`. The residual-monitor form
`G(x) = g_0(1 + α · |ΔS|)^(-1)` is recorded but not wired; `α` is unset.

### Item 2c — M_E shape

**Blocker:** RES-600 treats `M_E` as a scalar field (Axiom C); RES-601
§7 writes `M_E^(ij)`, suggesting a matrix. The shape is ambiguous.

**Interface:** `RheologyCoordinates.M_E`.

**Candidate:** RES-606 §4 chooses scalar × identity for the candidate
path. This makes the assembled metric conformal — a scalar rescaling
of identity with no directional content. Directional content is
deferred until channel weights exist.

### Item 3 — positive-definiteness of the full metric

**Blocker:** the SPD utility is ready, but `g_ij` cannot be instantiated
without items 1 and 2.

**Status:** waiting on items 1 and 2.

## Open — analysis items

These do not block the bridge but are unresolved.

| Item | Blocker |
|---|---|
| Cheeger bound for the specific hypergraph | sketch only |
| Tikhonov constants `C_1`, `C_2` | symbolic |
| Linear neighborhood size | not bounded |
| Cubic residual bound away from `Ψ_B` | not bounded |

## Open — data items

| Item | Blocker |
|---|---|
| Real-trajectory ε-sweep | requires a `.npy` with shape `[K ≥ 3, T, D]` and a decaying slow coordinate. Code is ready: `python scripts/run_fep_sweep.py --data trunk.npy`. |

## What cannot be done in code

Items 1–2c cannot be resolved by writing Python. They require source
derivations from the physics layer. Any code that pretends to supply
them by taking `Re_ε`, `G`, or `M_E` as inputs is a substitute in the
sense of RES-602 §5.4, and must be labelled as such.

## What is a candidate vs what is the canonical bridge

The distinction matters. RES-606 provides closed forms for items 1–2
using existing in-repo locks and tunable parameters. Those forms are
labelled **candidate** throughout. The canonical bridge stays locked
behind `BridgeMetricHead` until the source derivations replace the
candidates.

A candidate implementation is available as
`CandidateBridgeMetricHead` in `geometry.py` for experimentation.
Its docstring declares it a **structural proxy substitute** per
RES-602 §5.4.

## Read next

- [FEP Reduction Bridge](fep-reduction.md) — RES-600
- [Non-Dual Adaptation Layer](non-dual-adaptation.md) — RES-601
- [Two-Head Integration Note](integration.md) — RES-602
- [leCore Integration Bridge](lecore-bridge.md) — RES-605
