---
doc: RES-510
title: Titanos Application Note
status: draft
depends_on: [RES-200, RES-302, RES-303, RES-402]
referenced_by: [RES-501]
---

# Titanos Application Note

Titanos is a recurrent-depth reasoning prototype built on the frozen
Resileos-QAI contracts. It consumes `ResidualCore`, `SigmaGate`,
`route_signals`, and the control packet; it produces `Answer` objects with
full provenance. It does not modify any contract.

## Architecture

    Prelude          encode query into a hyperdimensional probe
    Recurrent Block  frozen ResidualCore applied N times, weight-shared
    Router           SigmaGate → route_signals → one of three bands
    Coda             substrate readout + cleanup + provenance

## Three routing bands

| Band | Condition | Behavior |
|---|---|---|
| CLASSICAL | similarity ≥ `classical_conf` | single retrieval, done |
| QUANTUM_SIM | `abstention_gate` ≤ similarity < `classical_conf` | Monte-Carlo superposition over K sparse perturbations; hard readout; cleanup |
| ABSTAIN | similarity < `abstention_gate` | no answer; reason returned |

## Consecutive volume escalation

The recurrent loop reads `volume_ok` from each packet. `SigmaGate` tracks
consecutive failures and escalates to `CLEANUP` after `k=3`, exactly as
RES-303 trigger 3 specifies. Routing between gate, volume, and abstention
uses `route_signals` — the frozen precedence — not a parallel priority.

## Quantum path

The `QUANTUM_SIM` band is a **labeled simulation**:

- Real: the superposition (linear sum) and the readout (hard collapse).
- Simulated: the parallelism. K perturbations are generated and bundled on
  classical hardware.

Every `Answer` that used this band is tagged `mode="QUANTUM_SIM"`. It is
never reported as `CLASSICAL` and never claimed to be a real quantum
computation. Real quantum acceleration remains gated behind RES-501.

## Honest limits

- Not an LLM. No text generation, no language understanding beyond the
  thin regex front-end.
- Not a real quantum computer.
- Not trained. `learn()` writes directly to the accumulator; there are no
  gradients anywhere in this module.
- Capacity scales as ~d/log(d). Above ~10,000 facts at `dim=10000`,
  crosstalk dominates and cleanup memory becomes necessary.

## Integration

Titanos consumes:

- `ResidualCore` (RES-200) — as the recurrent block, weight-shared across loops
- `SigmaGate` (RES-303) — as the regime router
- `route_signals` (RES-302) — as the abstention state machine
- `Packet` (RES-201) — as the per-loop artifact

Titanos produces:

- `Answer` with `value`, `confidence`, `status`, `mode`, `loops`, `path`,
  `reason`, `loop_history`, `gate_state`

## Next gates

1. Persistence — **done** (`save` / `load`).
2. NLP front-end — **done** (regex, off the reasoning path).
3. Formal `(X, Y)` measurement — see RES-402 wiring; Titanos must appear
   in the formal report only after `(X, Y)` are declared and met.
4. Real quantum hand-off — RES-501 still applies. Not before (3) closes.

## Read next

- [Classical Core](../200-core/classical-core.md) — RES-200
- [Abstention](../300-substrate/abstention.md) — RES-302
- [Sigma Gate](../300-substrate/sigma-gate.md) — RES-303
- [Roadmap](roadmap.md) — RES-501
