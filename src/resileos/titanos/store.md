"""Disk-backed storage engine for Titanos (RES-320).

Replaces the in-memory band dicts with memory-mapped int32 accumulators,
one file per relation. Facts append to a binary WAL with fixed-width
24-byte records (3 x int64). Metadata writes on flush() or close(), not
per operation.

Layout under data_dir:
    titanos_metadata.json    versioned metadata (relations, counts)
    titanos_wal.bin          append-only fact log
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
from pathlib import Path
from typing import Generator, Iterable, Optional

import numpy as np

DIM_MIN = 8
META_VERSION = 1
WAL_RECORD = struct.Struct("<3q")
WAL_RECORD_SIZE = WAL_RECORD.size
NAME_MAX = 128


def _safe_name(name: str) -> str:
    if not name or len(name) > NAME_MAX:
        raise ValueError(f"relation name must be 1..{NAME_MAX} chars")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


class DiskBandStore:
    """Memory-mapped accumulator store with append-only fact log.

    Usage:
        store = DiskBandStore("data/titanos", dimension=10000)
        view = store.band_view("has_property")   # numpy int32 view
        view += entity_vec * relation_vec        # in-place accumulate
        store.append_fact(sid, rid, oid)
        store.flush()
        store.close()

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

        self._bands: dict[str, mmap.mmap] = {}
        self._band_fds: dict[str, int] = {}
        self._wal_fd: Optional[int] = None
        self._lock = threading.RLock()
        self._closed = False

        self._meta = self._load_meta()
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

    def _open_wal(self) -> None:
        flags = os.O_RDONLY if self.read_only else (
            os.O_RDWR | os.O_CREAT | os.O_APPEND
        )
        self._wal_fd = os.open(str(self._wal_path), flags, 0o644)

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
    def append_fact(self, subject_id: int, relation_id: int, object_id: int) -> None:
        """Append one fact to the WAL. 24 bytes. Atomic on POSIX for
        writes under PIPE_BUF."""
        if self.read_only:
            raise PermissionError("store is read-only")
        if self._wal_fd is None:
            raise RuntimeError("WAL is not open")
        buf = WAL_RECORD.pack(int(subject_id), int(relation_id), int(object_id))
        os.write(self._wal_fd, buf)
        self._meta["total_facts"] = int(self._meta["total_facts"]) + 1

    def append_facts(self, facts: Iterable[tuple[int, int, int]]) -> int:
        """Batch append. One write per call, one metadata update."""
        if self.read_only:
            raise PermissionError("store is read-only")
        if self._wal_fd is None:
            raise RuntimeError("WAL is not open")
        buf = bytearray()
        n = 0
        for s, r, o in facts:
            buf += WAL_RECORD.pack(int(s), int(r), int(o))
            n += 1
        if n:
            os.write(self._wal_fd, bytes(buf))
            self._meta["total_facts"] = int(self._meta["total_facts"]) + n
        return n

    def iter_facts(self) -> Generator[tuple[int, int, int], None, None]:
        """Yield every fact in the WAL, in order."""
        if not self._wal_path.exists():
            return
        with open(self._wal_path, "rb") as f:
            while True:
                chunk = f.read(WAL_RECORD_SIZE)
                if not chunk:
                    break
                if len(chunk) != WAL_RECORD_SIZE:
                    break
                yield WAL_RECORD.unpack(chunk)

    def fact_count(self) -> int:
        return int(self._meta["total_facts"])

    def rebuild_from_wal(
        self,
        entity_vectors: dict[int, np.ndarray],
        relation_vectors: dict[int, np.ndarray],
        relation_id_to_name: dict[int, str],
    ) -> int:
        """Reconstruct accumulators by replaying the WAL.

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
        for s_id, r_id, o_id in self.iter_facts():
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


__all__ = ["DiskBandStore", "WAL_RECORD_SIZE", "META_VERSION"]
