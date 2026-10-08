---
doc: RES-500
title: Behavioral Notes
status: stable
depends_on: [RES-303, RES-402]
referenced_by: [RES-501]
---

# Behavioral Notes

Operational semantics that sit downstream of the frozen contracts. None of
these reopen an interface; they describe how frozen contracts behave under
edge conditions.

## 1. REPULSE hold counter

Optional. Declared as `repulse_hold` in the run config. When set above zero,
the machine holds `REPULSE` for at most `repulse_hold` steps before falling
through to `ABSTAIN`. When zero, the machine relies on the parity state alone
to exit `REPULSE`.

## 2. Volume-failure escalation

Volume-failure escalation is routed through the sigma-1 gate, not the
abstention machine. Concretely: after `sigma1_k = 3` consecutive
`volume_ok == False` steps, the gate fires with `sigma1_action = "CLEANUP"`.
This matches RES-303 trigger 3 and the sigma-1 precedence rule.

## 3. ΔS variance as heuristic shift proxy

`rolling_DeltaS_var` is a heuristic for distribution shift. It is convenient
because `ΔS` is a scalar monitor, not a distributional summary of `F_res`.
The alternative `F_res_stat` uses the same window and trigger block; its
semantics are an absolute multiplier on the warm-up statistic rather than a
variance ratio. The config loader must record which interpretation was used.

## 4. Part A ↔ current schema round-trip

The residual-scale mapping `k = round(s / ε)` with clamp to `[-16, +16]` is
exact inside the open interval `(-16, +16)` and saturates at the endpoints.
Round-trip tolerance is therefore “exact inside the open interval, saturated
at the endpoints.”

## 5. `sigma1_action = REPULSE_ABSTAIN` persistence

Holds until the next sigma-1 evaluation or an explicit reset by the gate.
The evaluation cadence is declared in the run config.

## Read next

- [Roadmap](roadmap.md) — RES-501
