# RES-310: Hierarchical Encoding

**Status:** Draft
**Layer:** Composition (above codex, above frozen substrate)
**Depends on:** RES-306 (phasor graph), `codex.PhiPhaseCodex`
**Blocks:** RES-311 (streaming state), RES-312 (mask stack), RES-313 (composition capacity), RES-315 (modulation interface)

---

## 1. Purpose

The codex bundles one window of tokens into one hypervector. VSA recall
capacity per bundle is approximately `C(dim) = floor(dim / (2 ln dim))` items
before crosstalk exceeds cleanup SNR. At dim=512, C ≈ 41. At dim=1024, C ≈ 74.

Trillion-token modulation cannot be a flat bundle. It must be a tree. This
spec defines the tree, its encoder, its query, and the guarantees it does
and does not provide.

---

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

---

## 3. Position codes

At each position-code level `L ∈ [0, K)`, `pos_codes[L]` is an array of
constant-magnitude phasors:

    pos_codes[L][i] = phi_phasor(i, dim, salt=LEVEL_SALT * L + 17)

Position codes at different levels use different salts and are statistically
independent. Codes within a level are near-orthogonal for distinct indices.

Binding: `bound = codex.bind(child_hv, pos_codes[L][i])`.
Unbinding: `child_hv ≈ codex.unbind(bundle_hv, pos_codes[L][i])`.

---

## 4. Encoder

Buffers, one per level, hold child HVs and their spans.

- `buffers[0]` holds token HVs.
- `buffers[L]` for L > 0 holds level-L packet HVs.

When `len(buffers[L]) == capacities[L]`, the buffer flushes: children are
bound to their positions, bundled, and the result is appended to
`buffers[L+1]` (or emitted as a top-level packet if `L == K-1`).

A flush at level L can fill `buffers[L+1]`, triggering a cascade at L+1.
Cascades continue until no buffer is full.

**API.**

    push(token_id) -> list[HierarchicalPacket]
    push_many(tokens) -> list[HierarchicalPacket]
    flush() -> list[HierarchicalPacket]
    reset() -> None

All three return the full list of packets emitted during the call, in the
order they closed. This is required for streaming: a single push can close
multiple packets when a cascade propagates to the top.

---

## 5. Span tracking

Every buffered item carries a half-open token-index interval `[start, end)`.

- Token at global index `i` has span `[i, i+1)`.
- A level-L packet spanning children with intervals `[s_0, e_0), ...,
  [s_{n-1}, e_{n-1})` has span `[s_0, e_{n-1})`.

Spans are stored per buffer entry so cascaded flushes report correct
coverage even after partial flushes at intermediate levels.

---

## 6. Query

A level-L packet's children are indexed by `pos_codes[L-1]`. Descent from a
level-K packet walks `pos_codes[K-1]`, then `pos_codes[K-2]`, ..., then
`pos_codes[0]`, and finally cleans up at the token codebook.

**API.**

    locate(bundle_hv, pos_level, target_hv) -> (position, similarity)
    retrieve(bundle_hv, pos_level, position) -> child_hv
    descend_to_token(packet, path) -> (token_id, raw_token_hv)

`path` must have length `packet.level`. `path[0]` indexes `pos_codes[
packet.level - 1]`; `path[-1]` indexes `pos_codes[0]`.

Encoder and query share `pos_codes`. Two encoders with identical
`(dim, capacities, seed)` interoperate.

---

## 7. Non-claims

- **No compression claim.** The tree re-encodes the token stream so recall
  survives at scale. It does not reduce information content.
- **No semantic claim.** "Window", "paragraph", "document" are capacity-driven
  groupings, not linguistic units.
- **No learned structure.** Position codes are deterministic given `(dim,
  level, index)`. No training signal is consumed.
- **No bidirectional access.** Descent requires a position path. Retrieval
  of an arbitrary token without a path is RES-311's problem.
- **No downstream utility claim.** Whether a corpus-level packet is useful
  to a modulation consumer is RES-315's problem.
- **No capacity guarantee at depth.** The formula `C(dim) = floor(dim / (2 ln
  dim))` bounds crosstalk *per bundle*. Crosstalk accumulation across depth
  is measured, not assumed. See §8.

---

## 8. Open questions

1. **Depth degradation.** A level-K bundle contains tokens re-bundled K
   times. The empirical descent accuracy at each depth K must be measured
   before any trillion-token reach claim. `tests/test_hierarchy.py` provides
   the harness; the curve itself is RES-313's input.
2. **Position codebook length.** `pos_codes[L]` must have at least
   `capacities[L]` entries. If `dim` is small, `C(dim)` may be smaller than
   a user-supplied capacity. The encoder validates this and raises.
3. **Partial-flush crosstalk.** A partial flush (fewer than `C(dim)` items)
   has lower crosstalk. Norm is renormalized by `bundle`. Whether variable
   bundle size is preferable to padding is RES-313's question.
