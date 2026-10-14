doc: RES-310
title: Hierarchical Encoding
status: draft
depends_on: RES-306
referenced_by: RES-311, RES-312, RES-313, RES-315

# Hierarchical Encoding

The codex bundles one window of tokens into one hypervector. VSA recall
capacity per bundle is approximately `C(dim) = floor(dim / (2 ln dim))` items
before crosstalk exceeds cleanup SNR. At dim=512, C ≈ 41. At dim=1024, C ≈ 74.
Trillion-token modulation cannot be a flat bundle. It must be a tree. This
spec defines the tree, its encoder, its query, and the guarantees it does and
does not provide.

## 1. Purpose

The codex is a single-level encoder. It has no notion of a paragraph, a
document, or a corpus. At trillion scale, the hierarchy is the only way to
represent structure above the window without exceeding per-bundle capacity.

## 2. Level indexing

The tree has discrete levels. Level 0 is the token level. Level L > 0 is a
bundle of level-(L-1) items.

- **Level-1 packet** — a bundle of tokens. Positions indexed by `pos_codes[0]`.
- **Level-2 packet** — a bundle of level-1 packets. Positions by `pos_codes[1]`.
- **Level-L packet** — a bundle of level-(L-1) packets. Positions by `pos_codes[L-1]`.

A configuration `capacities = [c_0, c_1, ..., c_{K-1}]` defines:

- `c_L` = number of level-L items per level-(L+1) packet.
- Highest packet level = `K`.
- Number of position-code streams = `K`.

`c_0` is tokens per window. `c_1` is windows per paragraph. Etc.

## 3. Position codes

At each position-code level `L ∈ [0, K)`, `pos_codes[L]` is an array of
constant-magnitude phasors:

    pos_codes[L][i] = phi_phasor(i, dim, salt=LEVEL_SALT * L + 17)

Position codes at different levels use different salts and are statistically
independent. Codes within a level are near-orthogonal for distinct indices.

Binding:

    bound = codex.bind(child_hv, pos_codes[L][i])

Unbinding:

    child_hv ≈ codex.unbind(bundle_hv, pos_codes[L][i])

## 4. Encoder

Buffers, one per level, hold child HVs and their spans.

- `buffers[0]` holds token HVs.
- `buffers[L]` for L > 0 holds level-L packet HVs.

When `len(buffers[L]) == capacities[L]`, the buffer flushes: children are bound
to their positions, bundled, and the result is appended to `buffers[L+1]` (or
emitted as a top-level packet if `L == K-1`). A flush at level L can fill
`buffers[L+1]`, triggering a cascade at L+1. Cascades continue until no buffer
is full.

**API.**

    push(token_id) -> list[HierarchicalPacket]
    push_many(tokens) -> list[HierarchicalPacket]
    flush() -> list[HierarchicalPacket]
    reset() -> None

All three return the full list of packets emitted during the call, in the order
they closed. This is required for streaming: a single push can close multiple
packets when a cascade propagates to the top.

## 5. Span tracking

Every buffered item carries a half-open token-index interval `[start, end)`.

- Token at global index `i` has span `[i, i+1)`.
- A level-L packet spanning children with intervals `[s_0, e_0), ..., [s_{n-1}, e_{n-1})` has span `[min(s), max(e))`.

Spans are carried on the packet, not on the hypervector. They are bookkeeping
for RES-311's streaming state and for any consumer that needs to map a packet
back to a token range.

## 6. Query

    query(bundle_hv, pos_codes, path) -> complex128[dim]

`path` is a list of level indices. The query descends the tree by unbinding
each level's position code in turn. The result is an approximation of the
leaf hypervector at the path.

    query(bundle_hv, pos_codes, [i]) -> approximation of level-1 child i
    query(bundle_hv, pos_codes, [i, j]) -> approximation of level-2 grandchild (i, j)

Each unbind adds crosstalk. The depth penalty in RES-313 §2 applies.

## 7. Non-claims

- No capacity guarantee above the per-bundle bound. The tree does not exceed
  `C(dim)` at any level.
- No semantic claim. Levels are depth-ordered, not semantically ordered.
- No learned structure. Capacities are supplied by the caller. The encoder does
  not search for optimal capacities.
- No claim that the tree captures language structure. It captures token
  co-occurrence at multiple scales. Whether that is "structure" is a separate
  question.
- No bidirectional access. Descent is unidirectional.

## 8. Open questions

- **Optimal capacities.** Given `dim` and a corpus, how should `c_0, c_1, ...`
  be chosen? The capacity law (RES-313) says the depth penalty depends on
  `n_max / D`, so smaller `c_L` means less penalty per level but more levels.
- **Level count.** How many levels before the top-level packet represents the
  whole corpus? This is a design choice, not derived.
- **Salt collisions.** `LEVEL_SALT * L + 17` is a heuristic. Are there `L`
  values where salts collide?
