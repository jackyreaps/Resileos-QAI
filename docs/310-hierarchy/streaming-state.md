doc      | RES-311
title    | Streaming Substrate State
status   | draft
depends_on | RES-310 (hierarchical encoding), RES-200 (classical core)
referenced_by | RES-313 (composition capacity), RES-315 (modulation interface)

# Streaming Substrate State

The hierarchy encoder (RES-310) is stateless with respect to time. It flushes
buffers, emits packets, and forgets. Trillion-token modulation requires a state
that persists across the entire stream: a running context that each new window
updates and that the modulation consumer can read at any point.

This document defines that state, its update rule, and what it does and does not
guarantee. It does not define the modulation consumer. That is RES-315.

## 1. Why a persistent state exists

A window-by-window encoder re-derives its hypervector from scratch every 32 to 64
tokens. There is no carry-forward context. At trillion scale, this is not merely
inefficient — it is structurally wrong. Language has long-range dependence, and
a substrate that cannot represent "the current document" or "the current
discourse segment" cannot modulate a downstream model that depends on them.

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
