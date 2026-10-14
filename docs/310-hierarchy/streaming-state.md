doc: RES-311
title: Streaming Substrate State
status: draft
depends_on: RES-310, RES-200
referenced_by: RES-313, RES-315

# Streaming Substrate State

The hierarchy encoder (RES-310) is stateless with respect to time. It flushes
buffers, emits packets, and forgets. Trillion-token modulation requires a state
that persists across the entire stream: a running context that each new window
updates and that the modulation consumer can read at any point.

This document defines that state, its update rule, and what it does and does not
guarantee. It does not define the modulation consumer. That is RES-315.

## 1. Why a persistent state exists

A window-by-window encoder re-derives its hypervector from scratch every 32 to
64 tokens. There is no carry-forward context. At trillion scale this is not
merely inefficient — it is structurally wrong. Language has long-range
dependence, and a substrate that cannot represent "the current document" or
"the current discourse segment" cannot modulate a downstream model that depends
on them.

The streaming state is that representation. It is a single hypervector,
`stream_hv`, updated once per emitted packet by the hierarchy encoder.

## 2. State contract

| Field | Type | Persists across | Updated by |
|-------|------|-----------------|------------|
| `stream_hv` | `complex128[dim]` | Entire stream | Every emitted packet |
| `stream_span` | `(start, end)` | Entire stream | Every emitted packet |
| `stream_packet_count` | `int` | Entire stream | Every emitted packet |
| `last_packet_level` | `int` | Entire stream | Every emitted packet |

`stream_hv` is the only field a consumer reads. The rest are bookkeeping for
inspection and for RES-313's depth accounting.

## 3. Update rule

When the hierarchy encoder emits a packet `p` with hypervector `hv_p`, level
`L_p`, and span `[s_p, e_p)`:

    stream_hv = normalize(stream_hv + decay**L_p * hv_p)
    stream_span = (min(stream_span.start, s_p), max(stream_span.end, e_p))
    stream_packet_count += 1
    last_packet_level = L_p

`decay` is a scalar in `(0, 1]`. It controls the effective window of the
running state. `decay = 1` means every packet ever emitted contributes equally —
the state is a corpus-wide bundle, and its recall capacity is the flat-bundle
capacity `C(dim)` from RES-310 §1. `decay < 1` means recent packets dominate —
the state is a decaying memory with an effective horizon of `1 / (1 - decay)`
packets.

The default is `decay = 1`. Rationale: a decaying state is a lossy state, and
RES-313's capacity law assumes the non-decaying form. `decay < 1` is an
optimization, not a default, and must be justified per application.

The `decay**L_p` factor weights packets by their level. A level-3 packet
represents `c_0 * c_1 * c_2` tokens; a level-1 packet represents `c_0`. Without
level weighting, the state over-represents the finest granularity.

## 4. Readout

At any point, a consumer can read:

    readout() -> complex128[dim]

This returns `stream_hv`. Nothing else. The consumer is responsible for
interpreting it.

Two optional readouts are defined for inspection:

    entropy() -> float

Returns the effective number of packets contributing to `stream_hv`, estimated
from the norm: if `stream_hv` is a sum of `N` unit-norm random phasors, its norm
is `sqrt(N)` in expectation. `entropy()` returns `||stream_hv||**2`.

    snapshot() -> dict

Returns the full state dict. Used by tests and by RES-313's depth accounting.

## 5. Persistence and reset

    save(path) -> None
    load(path) -> None
    reset() -> None

`save` and `load` serialize `stream_hv` and the bookkeeping fields to a single
`.npz` file. `reset` returns the state to its initial value: zero vector, empty
span, zero count.

The state is deterministic given `(dim, seed, decay)` and the sequence of
emitted packets. Two encoders with identical configuration produce identical
states from identical input streams.

## 6. Interaction with the hierarchy encoder

The encoder (RES-310) knows nothing about the streaming state. The streaming
state subscribes to the encoder's output stream. This separation is deliberate:
the encoder is a pure function of its input tokens; the state is a reducer over
the encoder's output. Either can be replaced without touching the other.

    enc = HierarchicalEncoder(dim=512, capacities=[32, 8, 4], seed=0)
    state = StreamState(dim=512, decay=1.0, seed=0)
    for packet in enc.push_many(tokens):
        state.update(packet)

## 7. Non-claims

- No semantic claim. `stream_hv` is not a representation of "meaning." It is a
  running bundle of packets. Its usefulness to a consumer is RES-315's problem.
- No capacity guarantee. The state's recall capacity is bounded by RES-313, not
  by this document. `entropy()` is a diagnostic, not a guarantee.
- No learning. The update rule is deterministic. No gradient flows into the
  state.
- No bidirectional access. The state is a single hypervector. Recovering an
  arbitrary token from it requires a position path, which the state does not
  carry. That is RES-310's descent, not this state.
- No long-range dependence claim. Whether `stream_hv` actually captures
  document-level structure is an empirical question, measured by RES-313.

## 8. Open questions

- **Effective horizon.** For `decay < 1`, what is the actual recall horizon as a
  function of `decay`, `dim`, and packet rate? This is a RES-313 input.
- **Level weighting.** Is `decay**L_p` the right level weight, or should the
  weight be `c_L` (the token count the packet represents)? The two differ when
  capacities are non-uniform.
- **State size.** A single `dim`-vector is the minimal state. Would a `(dim, r)`
  matrix — one row per oscillator band — preserve more structure? This is a
  RES-312 question, since bands are the mask stack.
- **Reset semantics.** At trillion scale, does the state ever reset? Per
  document? Per epoch? The contract does not decide.
