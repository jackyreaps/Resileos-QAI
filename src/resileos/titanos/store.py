"""Disk-backed storage engine for Titanos (RES-320, RES-332 temporal).

Replaces the in-memory band dicts with memory-mapped int32 accumulators,
one file per relation. Facts append to a binary WAL with fixed-width
24-byte records (3 x int64). Metadata writes on flush() or close(), not
per operation.

Temporal extension (RES-332):

    Validity intervals live in a parallel append-only sidecar,
    `titanos_validity.bin`, with fixed-width 16-byte records
    (2 x int64: valid_from_days, valid_to_days since 1970-01-01).
    -1 is the sentinel for None ("since forever" / "still true").

    The sidecar is created lazily on the first append that carries a
    non-None validity. On creation, sentinels are backfilled for
    existing WAL facts so the two files stay index-aligned.

    Existing stores without the sidecar read all facts as
    (None, None) — no migration required. This preserves backwards
    compatibility with stores written before the temporal extension.

    The WAL stays exactly 24 bytes per record; no format change.
    Band accumulators are time-agnostic (they add the bound vector
    regardless of validity). Temporal filtering happens at query time
    in Titanos.ask_list().

Layout under data_dir:
    titanos_metadata.json    versioned metadata (relations, counts)
    titanos_wal.bin          append-only fact log (24 bytes/record)
    titanos_validity.bin     append-only validity log (16 bytes/record)
                             — optional, present after first temporal
                             append
    band_<relation>.bin      int32 accumulator, dimension * 4 bytes

The WAL is load-bearing: rebuild_from_wal() reconstructs the accumulators
from scratch. If a band file is corrupted, delete it and rebuild.

Single-process. Multiple writers require external locking.
"""
from __future__ import annotations

import json
import mmap
import os
import struct
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Generator, Iterable, Optional

import numpy as np

DIM_MIN = 8
META_VERSION = 1
WAL_RECORD = struct.Struct("<3q")
WAL_RECORD_SIZE = WAL_RECORD.size
VALIDITY_RECORD = struct.Struct("<2q")
VALIDITY_RECORD_SIZE = VALIDITY_RECORD.size
NAME_MAX = 128

# Sentinel for None validity in the sidecar (-1 = "since forever" /
# "still true"). Chosen so it's distinct from any real day count.
_SENTINEL = -1
_EPOCH = date(1970, 1, 1)


def _safe_name(name: str) -> str:
    if not name or len(name) > NAME_MAX:
        raise ValueError(f"relation name must be 1..{NAME_MAX} chars")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def _iso_to_days(s: Optional[str]) -> int:
    """Convert ISO 8601 date string to days since 1970-01-01.
    None/empty -> _SENTINEL. Tolerates a datetime prefix (uses first 10 chars).
    """
    if s is None:
        return _SENTINEL
    s = str(s).strip()
    if not s:
        return _SENTINEL
    try:
        d = date.fromisoformat(s[:10])
    except ValueError:
        return _SENTINEL
    return (d - _EPOCH).days


def _days_to_iso(d: int) -> Optional[str]:
    """Inverse of _iso_to_days. _SENTINEL -> None."""
    if int(d) < 0:
        return None
    return (_EPOCH + timedelta(days=int(d))).isoformat()


class DiskBandStore:
    """Memory-mapped accumulator store with append-only fact log.

    Usage:
        store = DiskBandStore("data/titanos", dimension=10000)
        view = store.band_view("has_property")   # numpy int32 view
        view += entity_vec * relation_vec        # in-place accumulate
        store.append_fact(sid, rid, oid)
        store.flush()
        store.close()

    Temporal:
        store.append_fact(sid, rid, oid,
                          valid_from="1458-01-01",
                          valid_to="1834-01-01")
        for s, r, o, vf, vt in store.iter_facts(include_validity=True):
            ...

    Or as a context manager:
        with DiskBandStore("data/titanos", 10000) as store:
            ...
    """

    def __init__(
        self,
        data_dir: str | Path,
        dimension: int,
        *,
        read_only: bool = False,
    ) -> None:
        if dimension < DIM_MIN:
            raise ValueError(f"dimension must be >= {DIM_MIN}")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = int(dimension)
        self.read_only = bool(read_only)
        self._vec_bytes = self.dimension * 4

        self._meta_path = self.data_dir / "titanos_metadata.json"
        self._wal_path = self.data_dir / "titanos_wal.bin"
        self._validity_path = self.data_dir / "titanos_validity.bin"

        self._bands: dict[str, mmap.mmap] = {}
        self._band_fds: dict[str, int] = {}
        self._wal_fd: Optional[int] = None
        self._validity_fd: Optional[int] = None
        self._lock = threading.RLock()
        self._closed = False

        self._meta = self._load_meta()
        self._reconcile_validity_length()
        self._open_wal()

    # ── metadata ────────────────────────────────────────────────────
    def _load_meta(self) -> dict:
        if self._meta_path.exists():
            raw = json.loads(self._meta_path.read_text(encoding="utf-8"))
            if int(raw.get("version", 0)) != META_VERSION:
                raise RuntimeError(
                    f"metadata version mismatch: "
                    f"{raw.get('version')} != {META_VERSION}"
                )
            if int(raw.get("dimension", 0)) != self.dimension:
                raise RuntimeError(
                    f"metadata dimension {raw.get('dimension')} != "
                    f"configured {self.dimension}"
                )
            return raw
        return {
            "version": META_VERSION,
            "dimension": self.dimension,
            "relations": [],
            "total_facts": 0,
        }

    def _save_meta(self) -> None:
        if self.read_only:
            return
        tmp = self._meta_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._meta, indent=2), encoding="utf-8")
        tmp.replace(self._meta_path)

    def _count_wal_records(self) -> int:
        if not self._wal_path.exists():
            return 0
        return self._wal_path.stat().st_size // WAL_RECORD_SIZE

    def _count_validity_records(self) -> int:
        if not self._validity_path.exists():
            return 0
        return self._validity_path.stat().st_size // VALIDITY_RECORD_SIZE

    def _reconcile_validity_length(self) -> None:
        """If the validity sidecar exists but is shorter than the WAL,
        pad with sentinels so index alignment holds. No-op if sidecar
        is absent or already aligned."""
        if self.read_only:
            return
        if not self._validity_path.exists():
            return
        n_wal = self._count_wal_records()
        n_val = self._count_validity_records()
        if n_val < n_wal:
            with open(self._validity_path, "ab") as f:
                f.write(
                    VALIDITY_RECORD.pack(_SENTINEL, _SENTINEL)
                    * (n_wal - n_val)
                )

    def _open_wal(self) -> None:
        flags = os.O_RDONLY if self.read_only else (
            os.O_RDWR | os.O_CREAT | os.O_APPEND
        )
        self._wal_fd = os.open(str(self._wal_path), flags, 0o644)

        # Open validity sidecar if it exists (present after first
        # temporal append or after _reconcile_validity_length).
        if self._validity_path.exists():
            flags = os.O_RDONLY if self.read_only else (
                os.O_RDWR | os.O_APPEND
            )
            self._validity_fd = os.open(
                str(self._validity_path), flags, 0o644
            )

    def _ensure_validity_file(self) -> None:
        """Lazily create the validity sidecar on the first temporal
        append. Backfills sentinels for any existing WAL facts so the
        two files are index-aligned. No-op if already open or
        read-only."""
        if self._validity_fd is not None:
            return
        if self.read_only:
            return

        n_wal = self._count_wal_records()

        if not self._validity_path.exists():
            # Fresh sidecar: write sentinels for existing WAL facts
            if n_wal > 0:
                with open(self._validity_path, "wb") as f:
                    f.write(
                        VALIDITY_RECORD.pack(_SENTINEL, _SENTINEL)
                        * n_wal
                    )
            else:
                # Touch the file so open with O_APPEND succeeds
                self._validity_path.touch()

        flags = os.O_RDWR | os.O_APPEND
        self._validity_fd = os.open(
            str(self._validity_path), flags, 0o644
        )

    # ── band files ──────────────────────────────────────────────────
    def _band_path(self, relation: str) -> Path:
        return self.data_dir / f"band_{_safe_name(relation)}.bin"

    def _open_band(self, relation: str) -> mmap.mmap:
        with self._lock:
            if relation in self._bands:
                return self._bands[relation]
            path = self._band_path(relation)
            if not path.exists():
                if self.read_only:
                    raise FileNotFoundError(f"band file missing: {path}")
                with path.open("wb") as f:
                    f.write(b"\x00" * self._vec_bytes)
                if relation not in self._meta["relations"]:
                    self._meta["relations"].append(relation)
                    self._save_meta()
            flags = os.O_RDONLY if self.read_only else os.O_RDWR
            fd = os.open(str(path), flags)
            access = mmap.ACCESS_READ if self.read_only else mmap.ACCESS_WRITE
            mm = mmap.mmap(fd, self._vec_bytes, access=access)
            self._band_fds[relation] = fd
            self._bands[relation] = mm
            return mm

    def band_view(self, relation: str) -> np.ndarray:
        """Return an int32 numpy view over the relation's accumulator.

        The view aliases the mmap. In-place arithmetic on the view
        updates the file. Call flush() to force the OS to persist.
        """
        if self._closed:
            raise RuntimeError("store is closed")
        mm = self._open_band(relation)
        return np.frombuffer(mm, dtype=np.int32, count=self.dimension)

    def read_band(self, relation: str) -> np.ndarray:
        """Copy of the accumulator, decoupled from the mmap."""
        return self.band_view(relation).copy()

    def write_band(self, relation: str, values: np.ndarray) -> None:
        if self.read_only:
            raise PermissionError("store is read-only")
        if values.shape != (self.dimension,):
            raise ValueError(
                f"values shape {values.shape} != ({self.dimension},)"
            )
        view = self.band_view(relation)
        view[:] = values.astype(np.int32, copy=False)

    def relations(self) -> list[str]:
        return list(self._meta["relations"])

    # ── WAL ─────────────────────────────────────────────────────────
    def append_fact(
        self,
        subject_id: int,
        relation_id: int,
        object_id: int,
        *,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
    ) -> None:
        """Append one fact to the WAL with optional validity (RES-332).

        valid_from / valid_to: ISO 8601 date strings, or None for
        "since forever" / "still true".

        If either validity field is non-None and the validity sidecar
        does not yet exist, it is created and backfilled with sentinels
        for existing WAL facts so the two files stay index-aligned.
        """
        if self.read_only:
            raise PermissionError("store is read-only")
        if self._wal_fd is None:
            raise RuntimeError("WAL is not open")

        has_validity = (valid_from is not None) or (valid_to is not None)
        if has_validity and self._validity_fd is None:
            self._ensure_validity_file()

        buf = WAL_RECORD.pack(int(subject_id), int(relation_id), int(object_id))
        os.write(self._wal_fd, buf)
        self._meta["total_facts"] = int(self._meta["total_facts"]) + 1

        if self._validity_fd is not None:
            vf = _iso_to_days(valid_from)
            vt = _iso_to_days(valid_to)
            os.write(self._validity_fd, VALIDITY_RECORD.pack(vf, vt))

    def append_facts(self, facts: Iterable) -> int:
        """Batch append. Facts may be:
            3-tuples (s, r, o)                -> validity (None, None)
            5-tuples (s, r, o, vf, vt)        -> explicit validity
        One write per call per file, one metadata update.
        """
        if self.read_only:
            raise PermissionError("store is read-only")
        if self._wal_fd is None:
            raise RuntimeError("WAL is not open")

        wal_buf = bytearray()
        val_buf = bytearray()
        n = 0
        has_any_validity = False

        for item in facts:
            if len(item) == 3:
                s, r, o = item
                vf_str, vt_str = None, None
            elif len(item) >= 5:
                s, r, o = item[0], item[1], item[2]
                vf_str, vt_str = item[3], item[4]
            else:
                continue
            wal_buf += WAL_RECORD.pack(int(s), int(r), int(o))
            vf = _iso_to_days(vf_str)
            vt = _iso_to_days(vt_str)
            if vf != _SENTINEL or vt != _SENTINEL:
                has_any_validity = True
            val_buf += VALIDITY_RECORD.pack(vf, vt)
            n += 1

        if n == 0:
            return 0

        if has_any_validity and self._validity_fd is None:
            self._ensure_validity_file()

        os.write(self._wal_fd, bytes(wal_buf))
        self._meta["total_facts"] = int(self._meta["total_facts"]) + n

        if self._validity_fd is not None:
            os.write(self._validity_fd, bytes(val_buf))

        return n

    def _iter_validity(self) -> Generator[tuple[int, int], None, None]:
        """Yield (valid_from_days, valid_to_days) aligned with WAL order.
        Facts beyond the validity file's end yield sentinels."""
        n_wal = self._count_wal_records()
        n_val = self._count_validity_records()

        if n_val > 0:
            with open(self._validity_path, "rb") as f:
                for _ in range(min(n_val, n_wal)):
                    chunk = f.read(VALIDITY_RECORD_SIZE)
                    if len(chunk) != VALIDITY_RECORD_SIZE:
                        break
                    yield VALIDITY_RECORD.unpack(chunk)

        for _ in range(max(0, n_wal - n_val)):
            yield (_SENTINEL, _SENTINEL)

    def iter_facts(
        self,
        include_validity: bool = False,
    ) -> Generator[tuple, None, None]:
        """Yield every fact in the WAL, in order.

        include_validity=False (default): 3-tuples (s, r, o) —
            backwards compatible with existing callers including
            rebuild_from_wal().

        include_validity=True: 5-tuples
            (s, r, o, valid_from_iso_or_None, valid_to_iso_or_None).
        """
        if not self._wal_path.exists():
            return

        validity_iter = self._iter_validity() if include_validity else None

        with open(self._wal_path, "rb") as f:
            while True:
                chunk = f.read(WAL_RECORD_SIZE)
                if not chunk:
                    break
                if len(chunk) != WAL_RECORD_SIZE:
                    break
                s, r, o = WAL_RECORD.unpack(chunk)
                if include_validity:
                    vf_days, vt_days = next(validity_iter, (_SENTINEL, _SENTINEL))
                    yield (
                        s, r, o,
                        _days_to_iso(vf_days),
                        _days_to_iso(vt_days),
                    )
                else:
                    yield (s, r, o)

    def fact_count(self) -> int:
        return int(self._meta["total_facts"])

    def temporal_count(self) -> int:
        """Number of facts with non-None validity (either bound)."""
        if not self._validity_path.exists():
            return 0
        n = 0
        with open(self._validity_path, "rb") as f:
            while True:
                chunk = f.read(VALIDITY_RECORD_SIZE)
                if len(chunk) != VALIDITY_RECORD_SIZE:
                    break
                vf, vt = VALIDITY_RECORD.unpack(chunk)
                if vf != _SENTINEL or vt != _SENTINEL:
                    n += 1
        return n

    def rebuild_from_wal(
        self,
        entity_vectors: dict[int, np.ndarray],
        relation_vectors: dict[int, np.ndarray],
        relation_id_to_name: dict[int, str],
    ) -> int:
        """Reconstruct accumulators by replaying the WAL.

        Bands are time-agnostic: validity is ignored during replay.
        The temporal log lives in the validity sidecar and is read at
        query time, not at rebuild time.

        entity_vectors:   id -> bipolar int32 vector (dim,)
        relation_vectors: id -> bipolar int32 vector (dim,)
        relation_id_to_name: id -> relation name (used for band files)

        Returns the number of facts replayed.
        """
        if self.read_only:
            raise PermissionError("store is read-only")
        for name in self._meta["relations"]:
            self.write_band(name, np.zeros(self.dimension, dtype=np.int32))
        n = 0
        for s_id, r_id, o_id in self.iter_facts(include_validity=False):
            name = relation_id_to_name.get(r_id)
            if name is None:
                continue
            sv = entity_vectors.get(s_id)
            ov = entity_vectors.get(o_id)
            rv = relation_vectors.get(r_id)
            if sv is None or ov is None or rv is None:
                continue
            self.band_view(name)[:] += (sv * rv * ov).astype(np.int32)
            n += 1
        self.flush()
        return n

    # ── persistence ─────────────────────────────────────────────────
    def flush(self) -> None:
        if self.read_only:
            return
        with self._lock:
            for mm in self._bands.values():
                mm.flush()
            # os.write to WAL and validity are already kernel-buffered;
            # fsync for durability
            if self._wal_fd is not None:
                try:
                    os.fsync(self._wal_fd)
                except OSError:
                    pass
            if self._validity_fd is not None:
                try:
                    os.fsync(self._validity_fd)
                except OSError:
                    pass
            self._save_meta()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            for mm in self._bands.values():
                try:
                    mm.flush()
                    mm.close()
                except (ValueError, BufferError):
                    pass
            for fd in self._band_fds.values():
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._bands.clear()
            self._band_fds.clear()
            if self._wal_fd is not None:
                try:
                    os.close(self._wal_fd)
                except OSError:
                    pass
                self._wal_fd = None
            if self._validity_fd is not None:
                try:
                    os.close(self._validity_fd)
                except OSError:
                    pass
                self._validity_fd = None
            self._save_meta()
            self._closed = True

    def __enter__(self) -> "DiskBandStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


__all__ = [
    "DiskBandStore",
    "WAL_RECORD_SIZE",
    "VALIDITY_RECORD_SIZE",
    "META_VERSION",
]
