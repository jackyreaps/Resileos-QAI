doc: RES-501
title: Roadmap
status: draft
depends_on: RES-500
referenced_by:

# Roadmap

Everything below sits downstream of the frozen core and substrate contracts.
Nothing in this document reopens RES-200 through RES-402.

## 1. Multichannel / dual-stream

Deferred from the current contract. A future extension may add 8-channel
residual write or a ventral / dorsal split. Any multichannel experiment must
declare itself as an extension and supply its own bundle contract. It does not
alter the single-channel contract.

## 2. Residual Ledger Bridge

Map control-packet fields onto a residual ledger (capacity figures and
ε = 1/64 quantum). This is a downstream re-encoding with its own capacity
contract. It does not reinterpret the exponent range [-16, +16] frozen in
RES-200.

## 3. Coherence engine hand-off

Packet → quantum-information device interface. Speculative. No speed-up or
coherence claim is made until experimental characterization.

## 4. Ghost-peptide / biological write

8 residual channels inherited from a residual V₄ structure as fixed write ports
for endocrine / microtubule scaffolding. Organizational only. Does not alter
the algebraic core.

## 5. LASLS integrity guard

Optional later integrity layer on the compressed binary factors. Derived from
the same unipotent triangular structure. Not required for generative
correctness.

## 6. Hierarchy / modulation layer (RES-310 ... RES-315)

The 310-series defines the composition layer above the codex. It is the
foundation for any downstream consumer that needs a running state, a
multi-resolution view, or a modulation signal.

| Doc | Status | What it settles |
|-----|--------|-----------------|
| RES-310 | draft | The tree. Capacity-driven levels. |
| RES-311 | draft | The state. Running hypervector, decay, level weighting. |
| RES-312 | draft | The stack. Layered masks, sheath transition. |
| RES-313 | draft | The bound. Composition capacity. Trillion-token negative result. |
| RES-314 | draft | The error. Empirical model, redundancy contract. |
| RES-315 | draft | The interface. Carrier spec, minimal experiment. |

The negative result in RES-313 §6 is the load-bearing constraint on this
series. It says the composed system cannot carry trillion distinguishable
items. Every downstream claim must survive that constraint. The modulation
interface (RES-315) is the only path that does, because it claims a projection,
not a memory.

Nothing in this series reopens RES-200 through RES-307. The hierarchy is a
downstream consumer of the frozen core and substrate contracts.

## 7. Open work (ordered by dependency)

| Priority | Item | Depends on |
|----------|------|------------|
| 1 | Verify orientation transfer fix for φ-compress | `core.py` `_maybe_contract` |
| 2 | Implement RES-310 hierarchical encoder | RES-310 spec |
| 3 | Implement RES-311 streaming state | RES-310 |
| 4 | Implement RES-312 mask stack | RES-311, RES-306 |
| 5 | Falsification test for RES-313 capacity law | RES-310, RES-311 |
| 6 | Measure RES-314 position-error curve | RES-310, RES-311 |
| 7 | Minimal experiment for RES-315 modulation | RES-310 ... RES-314 |

## 8. Non-goals

- No reopening of the frozen core.
- No claim of trillion-token recall. RES-313 rules it out.
- No quantum speedup claim. The quantum backend is gated and downstream.
- No trained codex. The codex is fixed.
- No claim that the substrate is a language model. It is a side-channel.

## Read next

- [Glossary](https://github.com/jackyreaps/Resileos-QAI/blob/main/docs/900-reference/glossary.md) — RES-900
- [Documentation Index](https://github.com/jackyreaps/Resileos-QAI/blob/main/docs/README.md) — RES-000
