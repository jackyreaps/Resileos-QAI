---
doc: RES-401-ternary
title: Ternary Front-End Factors (Opt-in under RES-401)
status: candidate  # probes run CPU 2026-11-03; see artifacts/report_ternary_acceptance.json
depends_on: [RES-200, RES-201, RES-401, RES-330]
related_to: [capacity-contract, growth-spine]
---

# Ternary Front-End Factors

## 1. Scope (hard)

| In scope | Out of scope |
|----------|----------------|
| Trainable **FrontEndEncoder** only | Frozen residual core (scar, volume guard, schedule) |
| Opt-in quantizer `{−1, 0, +1}` with STE | Claiming Resileos is an LLM / transformer |
| Same loss family: reconstruction + residual regularization | End-to-end gradients through core |
| Residual scales on ε-grid still absorb remainder | Silent packet schema break |

Default remains **bipolar** `{+1, −1}`. Ternary is an opt-in path on the training end.

## 2. Role

The classical core factorizes matrix blocks into bipolar factors plus residual scales (ε = 1/64 grid). That is low-bit residual compression with QAT on the front-end.

Ternary adds a **zero** state so sparse structure in W can be represented without forcing ±1. Residual layers and packet residual scales already exist to carry what zeros discard. Goal: higher reconstruction fidelity at similar bit cost. System identity is unchanged: residual core + Titanos store, not a generative language model.

## 3. Quantizer

Forward (default thresholds):

\[
q(x) =
\begin{cases}
+1 & x > \tau \\
0 & |x| \le \tau \\
-1 & x < -\tau
\end{cases}
\]

τ default: `0.05` (configurable). Optional group scales are a later sub-option; v1 uses global τ.

Backward: STE — treat ∂q/∂x ≈ 1 (identity STE, same family as current `ste_sign`), or clip STE outside a window if instability appears.

## 4. Packet / core compatibility

- **v1 (recommended):** Encoder emits ternary Ub/Vb for training loss only; when handing factors to the frozen core, map `0 → +1` via `factors_for_core()`, **or** emit a `factors_mode=ternary` experimental packet only under a new packet minor version after schema review.
- Frozen core `_factorize` continues bipolar until an explicit packet version bump.
- Capacity contract (C0–C8) unchanged: residual ledger full; prior bounded.

## 5. Acceptance (before claiming improvement)

| Probe | Pass sense |
|-------|------------|
| Reconstruction MSE vs bipolar baseline on same W blocks | ternary ≤ bipolar (or clear win on sparse W) |
| Scar / ΔS floors (RES-401 declared) | still met |
| Core packet encode/decode round-trip | no regression on bipolar path |
| Ops M1/M2 on Titanos path | unaffected (training front-end is offline of query path) |

## 6. Implementation order

1. `ste_ternary` + `FrontEndEncoder(mode="bipolar"|"ternary")` (default bipolar)
2. Unit tests: forward values in `{−1,0,1}`, bipolar path bit-identical
3. Train smoke on synthetic sparse vs dense W; log MSE
4. Only then consider packet schema extension

Do not block host G1 / strict M4 on this experiment.


## 7. Acceptance results (CPU, 2026-11-03)

Recorded in `artifacts/report_ternary_acceptance.json`.

| Probe | Result |
|-------|--------|
| MSE dense (bipolar / ternary) | 9.38 / **8.28** (ternary lower) |
| MSE sparse (bipolar / ternary) | 9.80 / **7.83** (ternary lower) |
| Core `step()` bipolar factors | ok |
| Core `step()` ternary→bipolar map | ok (zeros → +1) |
| Hopfield cap wire | 1024 |
| Ops M1/M2 | covered by `test_ops_metrics_inprocess` (pytest green) |

Default production mode remains **bipolar**. Ternary stays opt-in (`mode="ternary"`).
