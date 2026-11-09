doc: RES-332
title: Temporal Semantics — Chronos and Kairos
status: draft
depends_on: [RES-201, RES-320, RES-322, RES-327]
referenced_by: []

# Temporal Semantics

Every kairos is a chronos, but not every chronos is a kairos.
The distinction, not the attribution, is the design principle.

## 0. The distinction

- **Chronos** — sequential, measurable time. The interval during which
  a fact holds in the modeled world.
- **Kairos** — the opportune moment. The point at which a fact is
  retrieved, framed, and answered.

Every answer (kairos) happens at a moment in sequence (chronos). But
not every fact (chronos) is answered (kairos). Facts accumulate; only
some are queried at any given moment. The temporal structure of the
store is the interface between these two layers.

The temporal extension is not "add time to the store." It is: make
the chronos layer explicit so the kairos layer has correct input.

## 1. What each layer already does

| Layer | Already in | Status |
|---|---|---|
| Kairos | frames, sector, gate_state, status, capacity — all assigned at answer time | ✅ shipped (RES-327) |
| Chronos (ordering) | `facts` insertion order; `HierarchicalPacket.span_start/end`; `Hades` transaction timestamps | ⚠️ implicit |
| Chronos (validity) | — | ❌ missing |

The kairos layer is the right shape. It interprets *at the moment of
the query*. But it currently interprets facts that have no validity
interval — only insertion order. A fact learned today and a fact
learned five years ago are indistinguishable to the kairos layer.

## 2. Chronos layer: valid-time on facts

A fact gains `valid_from` and `valid_to`:

    valid_from : str | None   # ISO 8601, or None = "since forever"
    valid_to   : str | None   # None = "still true"

The tuple goes from `(s, r, o)` to `(s, r, o, valid_from, valid_to)`.
Old callers pass nothing → `(None, None)` → always valid. Backwards
compatible.

**Append-only.** A conflicting fact with overlapping validity does
*not* overwrite the prior fact. Both exist. Conflict resolution is the
kairos layer's job, not the store's. This is the same structural
commitment as `council.py`: conflicts surface, they don't get
averaged away.

## 3. Kairos layer: as-of query and conflict policy

`ask_list(..., as_of=...)` and SPARQL `AS OF "<iso>"` filter against
valid-time at query time. That filter *is* the kairos resolution:
given the current moment (or a specified one), which of the append-only
facts are chronos-valid?

    ask_list("Athens", "capital_of", as_of="1800-01-01")  # []
    ask_list("Athens", "capital_of", as_of="1900-01-01")  # ["Greece"]

When two chronos-valid facts conflict — same subject, relation, and
overlapping validity — the kairos layer must **choose explicitly**:

| Policy | Behaviour |
|---|---|
| `LATEST` | Return the fact with the most recent `valid_from` |
| `ALL` | Return all conflicting values; caller resolves |
| `CONFLICT` | Return status `CONFLICT` with both values in provenance |

**Default: `CONFLICT`.** Never silently pick. This is the same rule
`council.py` applies to hub conflicts and `verifiers.py` applies to
constraint violations.

## 4. What each layer guarantees

| Layer | What it protects | What it does not |
|---|---|---|
| Chronos | "this fact was true from T1 to T2" | "this fact is true now" |
| Kairos | "given this query at this moment, this is the answer" | "this fact was always the answer" |

The truth-engine claim requires both. Without chronos, the store is a
fact cache that can only answer current-state questions. Without
kairos, the store is a log that cannot resolve conflict.

The current state — kairos shipped, chronos implicit — is a store that
can answer "what does the store believe about X?" but not "what was
believed about X in 1900?" That is a defensible state for a
current-state truth engine. It is not a temporal truth engine.

## 5. Reference architecture

**APEX-MEM** (Amazon AGI, ACL 2026) implements the same two-layer
split for conversational memory:

- append-only event log with temporal grounding (chronos)
- retrieval-time conflict resolution by a multi-tool agent (kairos)

Reported: 88.88% on LOCOMO, 86.2% on LongMemEval. Those are the
benchmarks a temporal implementation should match or exceed.

**`getzep/graphiti`** is the storage-shape reference: append-only
facts in a property graph, retrieve as-of. The graph structure isn't
required — the append-only + as-of pattern is the transferable part.

## 6. What this does not specify

**Wall-clock timestamps.** The `facts` list preserves insertion order
(transaction-time), but `learn()` does not record wall-clock time.
Whether it should is a separate decision. Transaction-time suffices
for reconstruction; it does not suffice for "when was this learned?"
That is a distinct query class.

**Causal time.** "X was true *because* Y." Different schema
(`caused_by` edges), different query operator (`WHY`). Not in scope.

**Change detection.** "What changed about Athens between 1800 and
1900?" Requires a delta operator over the fact list grouped by
validity overlap. Additive; not specified here. APEX-MEM's
multi-tool retrieval likely covers this; the exact operator shape is
a design question.

**Interval algebra.** Whether `valid_from` and `valid_to` can be
open, whether adjacent intervals merge, whether touching endpoints
count as overlap. Assume ISO 8601 half-open intervals `[from, to)`
by default. Relaxing this is a later refinement.

## 7. Implementation order

1. **Schema extension** — fact tuple gains `valid_from`, `valid_to`
2. **`learn()` signature extension** — optional keyword args, default None
3. **`ask_list()` and SPARQL `AS OF`** — filter predicate
4. **`check_temporal` extension** — conflict detection on validity overlap
5. **Capacity metric M9** — temporal conflict rate on the 120-fact corpus
6. **`docs/400-operations/capacity-results.md`** — record M9 alongside M1–M8

Each step is testable in isolation. Step 1 is the only one that
requires migration handling.

## 8. Migration

Two options:

**Versioned schema.** `facts` list entries carry a version field.
Version 1 = `(s, r, o)` with implicit `(None, None)` validity.
Version 2 = `(s, r, o, valid_from, valid_to)`. Read path handles both.

**Migrate on load.** `Titanos.load()` reads version-1 entries, writes
them back with `(None, None)`. Destructive but simple.

Versioned is safer for persisted state. Migrate-on-load is fine for
ephemeral state and for the 120-fact corpus.

## 9. What this changes in the kairos layer

The frame-assignment logic in `gate-encoder.md` §1.1 does not change.
What changes is the *input*: the `rows` a frame renders are now
chronos-filtered before the frame is derived. A `NO_ROWS` from an
`AS OF` query means "no fact was chronos-valid at that moment" — a
different claim than "no fact exists" (which is what the store returns
today).

That distinction matters. `NO_ROWS` today means "not in the store."
After this extension, it means one of two things depending on the
query: "not in the store" (no `AS OF`) or "not true at the specified
time" (`AS OF`). The frame's `status` field should probably distinguish
these — `NO_ROWS` vs `NO_ROWS_AT_TIME` — but that's a kairos-layer
decision, not a chronos-layer one. Recorded as an open question.

## 10. Read next

- [Control Packet](../200-core/control-packet.md) — RES-201
- [Disk-Backed Band Store](../320-titanos/store.md) — RES-320
- [Query Language](../320-titanos/query.md) — RES-322
- [Answer Route](../320-titanos/answer.md) — RES-327
- [Documentation Index](../readme.md)
