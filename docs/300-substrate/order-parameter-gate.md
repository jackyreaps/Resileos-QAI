---
doc: RES-309
title: Order Parameter Gate
status: proposal
depends_on: [RES-200, RES-302, RES-305]
referenced_by: []
---

# Order Parameter Gate

A confidence gate derived from the Kuramoto order parameter of the
non-conservative operator's phase vector.

## 1. Definition

    R = (1/r) · |Σ_j exp(i·θ_j)|

where `θ ∈ R^r` is the phase vector of the non-conservative operator
(RES-200 §extension). `R ∈ [0, 1]`:

- `R = 1` when all `θ_j` are equal (all oscillators in phase)
- `R → 0` when the phases are uniformly distributed around the circle

`R` is read directly from the operator's `theta` field. It is a
standard Kuramoto order parameter. The same functional form appears in
the sibling repository (`EEG_hyperscan.py`; QD-TER v5.0 §3).

## 2. Gate

When `use_order_parameter_gate=True`:

    scale = floor + (1 - floor) · R
    confidence_gated = confidence_raw · scale

`floor ∈ [0, 1]` is `order_parameter_floor` (default 0.5). At `R = 1`,
`scale = 1` and the gate is a no-op. At `R = 0`, `scale = floor` and
confidence is reduced to `floor · confidence_raw`.

The gate applies in `_ask` and `analogy`, after `_cleanup` returns the
raw confidence and before the abstention thresholds are compared.

## 3. Rationale

The non-conservative operator's phase vector `θ` accumulates phase
from the parity monitor `μ`. When the phases drift apart, the operator's
`D = exp(i·θ)` diagonal no longer acts as a coherent rotation — it
becomes a scatter of independent rotations. The Kuramoto order
parameter measures that coherence directly.

The claim: `R` should gate retrieval confidence. High `R` → trust the
top match. Low `R` → abstain more readily.

This is a candidate. Whether the gate improves the abstention/accuracy
tradeoff on any given corpus is an empirical question, measured by
`test_report_gate_effect`.

## 4. Off by default

The gate is disabled by default (`use_order_parameter_gate=False`).
With the gate off, `confidence_gated = confidence_raw` and
`order_parameter_scale = 1.0`. All previous behavior is preserved.

Enable via:
- `TitanosConfig(use_order_parameter_gate=True)`
- `--order-parameter-gate` flag in the CLI demo

## 5. What is measured

The test file `tests/test_order_parameter_gate.py` reports:

- known mean confidence (gate off vs on)
- unknown mean confidence (gate off vs on)
- known accept rate (gate off vs on)
- unknown abstain rate (gate off vs on)
- R at the end of the drive

The test asserts only that the gate changes *something* when R < 1.
Whether the change is an improvement is reported, not asserted — a null
result is a valid outcome.

## 6. Interpretation

Three possible outcomes when the gate is enabled on the Greek corpus:

1. **Known accept rate unchanged, unknown abstain rate up.** The gate
   improves separation. Keep it.
2. **Both rates unchanged.** R stays near 1 on this corpus (the phase
   vector does not drift enough to matter at this scale). Neutral
   result; the gate is real but inactive here.
3. **Known accept rate down.** The gate is too aggressive. Either
   raise `order_parameter_floor` or leave the gate off.

The measurement decides. The gate is not claimed to help.

## 7. What this is not

- Not a quantum operation. `R` is a classical phase-coherence scalar.
- Not a replacement for the abstention thresholds. It scales the
  confidence that those thresholds consume.
- Not a language-model mechanism. It gates retrieval.

## 8. Read next

- [Classical Core](../200-core/classical-core.md) — RES-200 §extension
- [Abstention](abstention.md) — RES-302
- [Causal Sandbox Index](causal-sandbox.md) — RES-305
