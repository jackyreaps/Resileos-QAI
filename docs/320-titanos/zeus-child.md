doc: RES-324
title: Zeus Child (Residual Specialist)
status: draft
depends_on: [RES-307, RES-315, RES-320, RES-321, RES-322, RES-323]
referenced_by: []

# Zeus Child (Residual Specialist)

Zeus is an `AgencyChild` (RES-307) that composes structured answers
from the Titanos store and declines when the substrate field is
unlocked. It is not a second store, not a transformer replacement, and
not a generative head.

This document defines the handler contract against the actual RES-307
signatures, the query loop the caller must run, and the criteria under
which the agency group removes the child.

## 1. Doctrine

| Layer | Role |
|-------|------|
| Titanos (RES-320–322) | Durable exact memory |
| Ingest (RES-323) | Eat external sources into φ-ladder + store |
| leCore (RES-605, RES-608) | Gate and route external models and tools |
| **Zeus (this doc)** | Internal child: residual-conditioned structured answers |

Zeus does **not** route HTTP capabilities. That is leCore.
Zeus does **not** persist facts. That is Titanos.
Zeus **may** return `None` (decline); the parent falls through.

## 2. The real handler contract

RES-307 fixes the handler signature as:

    HandlerFn = Callable[[Any, str, str, bool], Any]

i.e. exactly four positional arguments:

    handler(parent, subject, relation, inverse) -> Answer | None

- `parent` is the caller's Titanos instance (or any object exposing
  `ask`, `ask_inverse`, `chain`).
- `subject`, `relation`, `inverse` are the query.
- The return is `Any | None`. `None` means Zeus declines; the caller
  may fall through to pure Titanos lookup.
- The `Answer` type is not defined in RES-307. Zeus returns whatever
  the parent's `ask` / `ask_inverse` / `chain` returns.

**There are no per-request keyword arguments for R, CSI, stream, or
stack.** The handler signature is fixed. Zeus reads its substrate
context through *closure*: the factory function binds the context
providers at construction time, and the handler calls them internally.

The factory is `make_zeus_handler` (see §7). Its keyword arguments
are captured once; the handler signature stays four positionals.

## 3. What Zeus reads (and how)

| Input | How Zeus gets it | Purpose |
|---|---|---|
| `parent.ask` / `ask_inverse` / `chain` | method call in handler | ground-truth lookup |
| Field R | `field_R_fn()` captured at factory time | R gate: decline when R is low |
| CSI | **not read by Zeus**; recorded by the caller after the handler returns | fitness signal for the group |
| `stream_hv` | `stream` object captured at factory time | reserved for Mode B |
| `stack_hv` | `stack` object captured at factory time | reserved for Mode B |
| `carrier` | `carrier` object captured at factory time | reserved for Mode B |

The R gate is the only substrate input Zeus actually uses in Mode A.
The stream, stack, and carrier are captured but not called until
Mode B (see §6).

Zeus writes no state into `ResidualCore`. The only mutable surfaces
it touches are the parent's read methods. Agency fitness is updated
by the caller, not by Zeus.

## 4. The query loop

RES-307 does **not** provide a top-level `handle` method. The caller
runs the loop manually:

    child = group.select()
    if child is None:
        return None
    answer = child.handler(parent, subject, relation, inverse)
    accepted = answer is not None
    group.record(child.name, csi=current_csi, accepted=accepted)
    group.evaluate_and_prune()      # optional, periodic

A helper that runs the whole loop is provided:

    from resileos.titanos.zeus import run_zeus_query

    answer = run_zeus_query(
        group, parent, subject, relation, inverse,
        csi_fn=lambda: current_csi,
        prune=True,
    )

`run_zeus_query` performs select → invoke → record → (optional) prune
in one call. If `csi_fn` is omitted, `csi=1.0` is recorded. If
`prune=False`, the caller is responsible for calling
`group.evaluate_and_prune()` on their own schedule.

## 5. Eat criteria

Eat criteria are RES-307 parameters, defined on `AgencyGroup.__init__`:

| Parameter | Default | Meaning |
|---|---|---|
| `eat_threshold_csi` | 0.35 | child edible if `mean_csi` below this |
| `eat_threshold_contrib` | 0.15 | child edible if `contribution` EMA below this |
| `min_queries_before_eat` | 10 | minimum routed queries before eating |
| `min_weight` | 0.05 | child fully inactive once `requested_weight` drops below |
| `absorption_rate` | 0.4 | `weight *= 1 - absorption_rate` at each eat step |

Eat is **gradual**. A child whose fitness crosses both thresholds does
not disappear immediately; each `evaluate_and_prune()` call reduces
its requested weight by a factor of `(1 - absorption_rate)`. Only when
`requested_weight < min_weight` does the child go inactive and enter
`group.eaten`.

This means a Zeus child that becomes unfit over a few queries loses
routing share first, then is excluded. It never has an abrupt
transition.

The thresholds are operational parameters, not derived invariants.
They are tuned per deployment.

## 6. Mode A vs Mode B

### Mode A — structured composer (ships)

No generative head. Zeus composes answers from:

- direct Titanos lookup (delegates to `parent.ask` / `ask_inverse`)
- composite relation expansion via `parent.chain`
- (future) SPARQL query against the store, if the parent exposes it

Returns whatever the parent returns. If the parent misses, Zeus
returns `None` and the caller falls through.

Mode A ships with Zeus. It requires no training and no external model.

### Mode B — carrier-modulated prose (gated)

When a downstream consumer needs prose that structured answers cannot
provide, Zeus may use the carrier (RES-315) to modulate a frozen
decoder. The carrier is the only trainable component. The substrate
and decoder remain frozen.

Mode B is gated on the RES-315 minimal experiment producing measurable
signal. If that experiment is flat, Mode B stays unimplemented and
Zeus remains Mode A only. The `carrier` argument to
`make_zeus_handler` reserves the slot; it is not called in Mode A.

## 7. Implementation

The module is `src/resileos/titanos/zeus.py`. It exports:

    ZeusConfig            # r_decline_threshold, max_hops
    make_zeus_handler     # factory returning a HandlerFn
    run_zeus_query        # select → handler → record → prune helper

Factory usage:

    from resileos.substrate.agency import AgencyGroup
    from resileos.titanos.zeus import (
        ZeusConfig, make_zeus_handler, run_zeus_query,
    )

    handler = make_zeus_handler(
        composite_relations={"colleague_of": ["knows", "works_at"]},
        field_R_fn=lambda: field.order_parameter(),
        stream=stream,
        stack=stack,
        carrier=carrier,               # reserved for Mode B
        cfg=ZeusConfig(r_decline_threshold=0.3, max_hops=4),
    )

    group = AgencyGroup()
    group.add_child("zeus", handler, weight=1.0)

    answer = run_zeus_query(
        group, titanos_singleton,
        subject="alice", relation="colleague_of", inverse=False,
        csi_fn=lambda: current_csi,
        prune=False,
    )

    if answer is None:
        answer = titanos_singleton.ask("alice", "colleague_of")

The factory captures `composite_relations`, `field_R_fn`, `stream`,
`stack`, `carrier`, and `cfg` once. The resulting handler is a plain
`HandlerFn` — four positionals, one return value.

## 8. What Zeus does not do

- **Does not train the substrate.** Residual core, Kuramoto field, and
  hierarchy are frozen from Zeus's perspective.
- **Does not train a decoder.** In Mode B, the decoder is frozen. Only
  the carrier trains, and that is a separate experiment.
- **Does not generate from scratch.** Mode A does not generate. Mode B
  generates only through a frozen decoder that the carrier modulates.
- **Does not replace Titanos.** Ground truth lives in the store.
- **Does not write to the residual core.** Zeus has no write path into
  the substrate.
- **Does not wrap the query loop.** The caller (or `run_zeus_query`)
  runs `select → handler → record → prune`.
- **Does not receive per-request R, CSI, stream, or stack.** Those are
  captured at factory time via closure.

## 9. Non-claims

- Not a claim that Zeus outperforms the parent. On requests the parent
  can answer directly, Zeus should decline and let the parent answer.
- Not a claim that Mode B will work. Mode B is gated on an experiment
  that has not run.
- Not a claim that the eat thresholds are optimal. They are
  operational parameters per RES-307 §0.
- Not a claim that Zeus is a language model. It is an agency child
  with a structured composer and an optional carrier-modulated escape
  hatch.
- Not a claim about "scar adjoint" or any formalization of the
  residual step. Zeus treats the packet and monitors as opaque state.

## 10. Open questions

- **SPARQL integration.** Zeus currently delegates to `ask` /
  `ask_inverse` / `chain`. If the parent exposes a SPARQL engine
  (RES-322), Zeus could compile composite relations into queries.
  Not implemented.
- **Cross-child coordination.** When multiple children are registered,
  `select()` is round-robin by lowest `query_count`, then highest
  weight. Zeus does not know which other children exist.
- **Retraining after eat.** If an eaten child is re-registered, its
  `local_csi` and `contribution` history is reset by `add_child`.
  Whether that is the right policy is not settled.
- **Mode B carrier wiring.** The `carrier` object is captured but
  never called. The integration with the RES-315 training loop is
  not specified.
- **Ground-truth verification.** The agreement check for `csi_fn`
  is caller-supplied. Zeus does not verify its own answers against
  the store.

## 11. Read next

- [Agency Hierarchy](../300-substrate/agency-hierarchy.md) — RES-307
- [Causal Sandbox Index](../300-substrate/causal-sandbox.md) — RES-305
- [Query Language and Execution](query.md) — RES-322
- [External Ingestion](ingestion.md) — RES-323
- [Eat Strategy](eat-strategy.md) — RES-325
- [Modulation Interface](../310-hierarchy/modulation-interface.md) — RES-315
- [leCore as Stomach](../600-qdter/lecore-stomach.md) — RES-608
- [Documentation Index](../readme.md)
