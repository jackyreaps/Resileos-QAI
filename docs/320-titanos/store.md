doc: RES-320
title: Disk-Backed Band Store
status: stable
depends_on: [RES-200]
referenced_by: [RES-321, RES-322]

# Disk-Backed Band Store

Titanos holds one int32 accumulator per relation. Each accumulator is a
`dimension`-length vector updated in place by `learn`. In the prototype
the accumulators lived in a Python dict. At the scale required for a
usable knowledge graph, the dict is the ceiling: all bands must fit in
RAM, and every `learn` call serializes the full state to JSON.

This document specifies `DiskBandStore`, which replaces the dict with
memory-mapped files and an append-only fact log. It does not change the
Titanos query semantics; it changes where the bytes live.

## 1. Layout

    data_dir/
        titanos_metadata.json    versioned metadata
        titanos_wal.bin          append-only fact log
        band_<relation>.bin      int32 accumulator, dimension * 4 bytes

`titanos_metadata.json` carries a version number and the dimension. If
either does not match the constructor arguments, the store refuses to
open. This prevents silently mixing two incompatible stores.

## 2. Accumulator files

Each relation gets one `band_<safe_name>.bin` file. `safe_name` replaces
every character outside `[A-Za-z0-9._-]` with `_`. Two relation names
that differ only in unsafe characters will collide; the caller is
responsible for using distinct names.

The file is exactly `dimension * 4` bytes. It is opened with `mmap` and
exposed to the caller as a NumPy view:

    store = DiskBandStore("data/titanos", dimension=10000)
    view = store.band_view("has_property")   # np.ndarray, int32
    view += entity_vec * relation_vec * object_vec

In-place arithmetic on the view writes through to the file. `flush()`
forces the OS to persist.

## 3. Write-ahead log

Every `learn` appends one 24-byte record to `titanos_wal.bin`:

    <subject_id:int64> <relation_id:int64> <object_id:int64>

IDs are dense integers assigned by the index (RES-321). The WAL is
append-only and never rewritten. It is the source of truth for
reconstruction.

`append_facts` batches many records into one `write` call. The
per-call metadata update is deferred to `flush`.

## 4. Reconstruction

If a band file is corrupted or deleted, `rebuild_from_wal` replays the
log:

    store.rebuild_from_wal(
        entity_vectors={1: vec_a, 2: vec_b, ...},
        relation_vectors={1: vec_r, ...},
        relation_id_to_name={1: "has_property", ...},
    )

The caller supplies the vector tables (which live in the index, not the
store). Replay writes every fact back into its band. The return value
is the number of facts replayed.

## 5. API

    DiskBandStore(data_dir, dimension, *, read_only=False)

    band_view(relation) -> np.ndarray          int32 view, aliases mmap
    read_band(relation) -> np.ndarray          copy, decoupled
    write_band(relation, values) -> None       overwrite
    relations() -> list[str]
    append_fact(s, r, o) -> None
    append_facts(iterable) -> int
    iter_facts() -> Iterator[(int, int, int)]
    fact_count() -> int
    rebuild_from_wal(entity_vectors, relation_vectors,
                     relation_id_to_name) -> int
    flush() -> None
    close() -> None

Context manager:

    with DiskBandStore("data/titanos", 10000) as store:
        ...

`read_only=True` opens band files read-only and rejects every write
path with `PermissionError`.

## 6. Concurrency

Single-process. `close()` and `flush()` are guarded by an internal lock,
but multiple writer processes are not supported. For multi-process
access, add `fcntl.flock` on the WAL file descriptor. This is a
deferred item.

## 7. Non-claims

- No compression. Accumulators are int32 dense vectors. Sparse storage
  is not attempted.
- No sharding. Every relation is one file. A relation whose
  accumulator exceeds available address space is not supported.
- No transactionality beyond the append-only WAL. A partially written
  fact record (last 24 bytes truncated) is silently ignored by
  `iter_facts`.
- No semantic guarantee. The store is a byte container. What the
  accumulators mean is RES-322's concern.

## 8. Open questions

- **fsync cadence.** `flush()` calls `mmap.flush()`, which returns to
  user space before the OS has written to disk. Durable-commit
  semantics require `os.fsync` on the underlying file descriptor.
- **Compaction.** The WAL grows without bound. A future version could
  checkpoint and truncate.
- **Dimension migration.** The metadata version check rejects a store
  opened at a different dimension. A migration path is not defined.

## 9. Read next

- [Dense Entity Index](index.md) — RES-321
- [Query Language](query.md) — RES-322
- [Documentation Index](../readme.md)
