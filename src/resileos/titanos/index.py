"""Bidirectional index for Titanos (RES-321).

Maps entity / relation names to dense integer IDs, holds the bipolar
vector per ID, and maintains a content-addressed hash index for
vector-to-ID lookup during cleanup.

Vector hashes are BLAKE2b-128 over the raw int32 vector bytes.
Collisions are astronomically unlikely at 128 bits; lookup still
verifies by direct comparison on miss.
"""
from __future__ import annotations

import hashlib
import struct
import threading
from typing import Iterator, Optional

import numpy as np

HASH_SIZE = 16
HASH_BYTES = HASH_SIZE


def vector_hash(vec: np.ndarray) -> str:
    """Stable 128-bit hash of a bipolar / int32 vector."""
    arr = np.ascontiguousarray(vec, dtype=np.int32)
    return hashlib.blake2b(arr.tobytes(), digest_size=HASH_SIZE).hexdigest()


class DenseEntityIndex:
    """Bidirectional name <-> id <-> vector index.

    Thread-safe for the operations exposed. Bulk insert is not atomic
    across the whole batch; call under external lock if needed.
    """

    def __init__(self, dimension: int) -> None:
        if dimension < 1:
            raise ValueError("dimension must be >= 1")
        self.dimension = int(dimension)
        self._name_to_id: dict[str, int] = {}
        self._id_to_name: dict[int, str] = {}
        self._id_to_vec: dict[int, np.ndarray] = {}
        self._hash_to_id: dict[str, int] = {}
        self._next_id = 0
        self._lock = threading.RLock()

    # ── lookup ──────────────────────────────────────────────────────
    def id_of(self, name: str) -> Optional[int]:
        return self._name_to_id.get(name)

    def name_of(self, entity_id: int) -> Optional[str]:
        return self._id_to_name.get(entity_id)

    def vector_of(self, entity_id: int) -> Optional[np.ndarray]:
        v = self._id_to_vec.get(entity_id)
        return None if v is None else v.copy()

    def id_by_hash(self, v_hash: str) -> Optional[int]:
        eid = self._hash_to_id.get(v_hash)
        if eid is None:
            return None
        return eid

    def __len__(self) -> int:
        return len(self._name_to_id)

    def __contains__(self, name: str) -> bool:
        return name in self._name_to_id

    # ── insert / update ─────────────────────────────────────────────
    def add(
        self, name: str, vector: np.ndarray, *, overwrite: bool = False
    ) -> int:
        """Insert or fetch an entity by name.

        If the name already exists and overwrite=False, returns the
        existing ID without changing the vector. If overwrite=True,
        replaces the vector and updates the hash index.
        """
        if not name:
            raise ValueError("name must be non-empty")
        arr = np.ascontiguousarray(vector, dtype=np.int32)
        if arr.shape != (self.dimension,):
            raise ValueError(
                f"vector shape {arr.shape} != ({self.dimension},)"
            )
        with self._lock:
            existing = self._name_to_id.get(name)
            if existing is not None and not overwrite:
                return existing

            new_hash = vector_hash(arr)
            if existing is not None:
                # remove old hash mapping if different
                old_vec = self._id_to_vec[existing]
                old_hash = vector_hash(old_vec)
                if old_hash != new_hash:
                    self._hash_to_id.pop(old_hash, None)
                self._id_to_vec[existing] = arr
                self._hash_to_id[new_hash] = existing
                return existing

            entity_id = self._next_id
            self._next_id += 1
            self._name_to_id[name] = entity_id
            self._id_to_name[entity_id] = name
            self._id_to_vec[entity_id] = arr
            self._hash_to_id[new_hash] = entity_id
            return entity_id

    def add_many(
        self, pairs: list[tuple[str, np.ndarray]], *, overwrite: bool = False
    ) -> list[int]:
        return [self.add(n, v, overwrite=overwrite) for n, v in pairs]

    # ── removal ─────────────────────────────────────────────────────
    def remove(self, entity_id: int) -> bool:
        """Remove by ID. Returns True if removed, False if not present."""
        with self._lock:
            name = self._id_to_name.pop(entity_id, None)
            if name is None:
                return False
            self._name_to_id.pop(name, None)
            vec = self._id_to_vec.pop(entity_id, None)
            if vec is not None:
                h = vector_hash(vec)
                # Only remove the hash entry if it points at this ID.
                if self._hash_to_id.get(h) == entity_id:
                    self._hash_to_id.pop(h, None)
            return True

    def remove_by_name(self, name: str) -> bool:
        eid = self._name_to_id.get(name)
        if eid is None:
            return False
        return self.remove(eid)

    # ── iteration ───────────────────────────────────────────────────
    def iter_names(self) -> Iterator[str]:
        return iter(self._name_to_id.keys())

    def iter_ids(self) -> Iterator[int]:
        return iter(self._id_to_name.keys())

    def iter_items(self) -> Iterator[tuple[int, str, np.ndarray]]:
        for eid, name in self._id_to_name.items():
            yield eid, name, self._id_to_vec[eid]

    # ── snapshot / persistence ──────────────────────────────────────
    def snapshot(self) -> dict:
        return {
            "dimension": self.dimension,
            "count": len(self._name_to_id),
            "next_id": self._next_id,
            "names": list(self._name_to_id.keys()),
        }

    def state_dict(self) -> dict:
        """Full serialisable state for pickling or JSON export.

        Vectors are stored as int lists. For large indexes prefer
        np.savez over this method.
        """
        return {
            "dimension": self.dimension,
            "next_id": self._next_id,
            "entries": [
                (eid, name, self._id_to_vec[eid].tolist())
                for eid, name in self._id_to_name.items()
            ],
        }

    @classmethod
    def from_state_dict(cls, state: dict) -> "DenseEntityIndex":
        idx = cls(dimension=int(state["dimension"]))
        for eid, name, vec in state["entries"]:
            arr = np.asarray(vec, dtype=np.int32)
            idx._name_to_id[name] = int(eid)
            idx._id_to_name[int(eid)] = name
            idx._id_to_vec[int(eid)] = arr
            idx._hash_to_id[vector_hash(arr)] = int(eid)
        idx._next_id = int(state["next_id"])
        return idx


__all__ = ["DenseEntityIndex", "vector_hash"]
