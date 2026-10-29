doc: RES-321
title: Dense Entity Index
status: stable
depends_on: [RES-320]
referenced_by: [RES-322]

# Dense Entity Index

Titanos stores facts as bipolar hypervectors keyed by name. Resolving a
name to its vector by scanning a dict is O(N). At the scale where the
store becomes disk-backed, the name lookup is the next bottleneck.

This document specifies `DenseEntityIndex`, which maintains dense
integer IDs alongside the name→vector mapping and adds a content-addressed
hash index for vector→ID lookup during cleanup.

## 1. Three maps

| Map | Direction | Purpose |
|---|---|---|
| `_name_to_id` | name → id | Resolve a query anchor to an ID |
| `_id_to_name` | id → name | Reverse for reporting |
| `_id_to_vec` | id → vector | Vector table for the store |
| `_hash_to_id` | vector hash → id | Cleanup: recall by content |

IDs are assigned densely from zero. The next ID is stored explicitly so
that removal does not cause ID reuse.

## 2. Vector hashing

    vector_hash(vec) -> str    # 16-byte hex, BLAKE2b-128

The hash is over the raw int32 bytes in C order. It is stable across
machines and Python versions. Collisions at 128 bits are astronomically
unlikely; the lookup is still a direct map, not a verified comparison.

Two vectors that differ in one component produce different hashes. The
hash is content-addressed, not identity-addressed.

## 3. API

    DenseEntityIndex(dimension)

    add(name, vector, *, overwrite=False) -> int
    add_many(pairs, *, overwrite=False) -> list[int]
    remove(entity_id) -> bool
    remove_by_name(name) -> bool

    id_of(name) -> int | None
    name_of(entity_id) -> str | None
    vector_of(entity_id) -> np.ndarray | None      # copy
    id_by_hash(v_hash) -> int | None

    iter_names() -> Iterator[str]
    iter_ids() -> Iterator[int]
    iter_items() -> Iterator[(id, name, vector)]

    __len__() -> int
    __contains__(name) -> bool

    snapshot() -> dict                              # counts only
    state_dict() -> dict                            # full, ints
    from_state_dict(state) -> DenseEntityIndex

## 4. Insert semantics

`add` with `overwrite=False` on an existing name returns the existing
ID without touching the vector. This makes `add` idempotent for the
common case where the same name is learned twice.

`add` with `overwrite=True` replaces the vector and updates the hash
index. The old hash entry is removed if it differs from the new one.

Duplicate content under different names produces two IDs that share a
hash bucket in `_hash_to_id`. The second insert overwrites the first
entry in the hash map; both names remain in `_name_to_id`. If
hash-based cleanup is used, only the most recent insert is reachable.

## 5. Removal semantics

`remove(entity_id)` clears all four maps for the given ID. It does not
decrement the next-ID counter. IDs are never reused.

`remove_by_name(name)` resolves the name first, then delegates.

Removal is O(1) for the ID and name maps. The hash map entry is only
removed if it points at the removed ID; if the hash was overwritten by
a later insert, the later entry stays.

## 6. Thread safety

The internal lock guards every mutating method. Reads are lock-free.
Bulk inserts via `add_many` are not atomic across the batch; callers
that need atomicity must hold an external lock.

## 7. Persistence

The index does not own a file. It serializes to and from a plain dict.
The store (RES-320) persists the vectors implicitly through the WAL;
reconstruction uses `state_dict` to rebuild the index.

## 8. Non-claims

- No compression. Every vector is stored in full, twice (once in
  `_id_to_vec`, once as a hash).
- No persistence format. `state_dict` is a Python dict; the caller
  chooses how to write it.
- No LRU or eviction. Insertion grows the index monotonically.
- No fuzzy lookup. `id_by_hash` is exact content addressing; near-miss
  recall requires the substrate's cleanup, not the index.

## 9. Open questions

- **Hash collisions.** At 128 bits the probability is negligible for
  the projected corpus size. A future version may want a second hash
  for verified comparison.
- **Persistence format.** `np.savez` over the vector table would be
  more compact than `state_dict`. Not implemented.
- **Bulk removal.** Removing a relation's worth of facts currently
  requires one `remove` call per entity. Not batched.

## 10. Read next

- [Disk-Backed Band Store](store.md) — RES-320
- [Query Language](query.md) — RES-322
- [Documentation Index](../readme.md)

- [gate-encoder.md](gate-encoder.md) — framework-native gate encoder and dual-sector mouth (RES-327-gate)
- [answer.md](answer.md) — `/api/v1/answer` contract (RES-327)
- [tools-and-frames.md](tools-and-frames.md) — tool schemas + Human-Medium frame tags
