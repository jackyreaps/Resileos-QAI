"""Separate store for hypervectors and consolidated patterns.

Stored facts stay in Titanos. This hub does not call ``learn`` and it
does not update a residual scar matrix. Visual paths do not use it.
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from resileos.moments import bind, bundle


class LatentHub:
    """In-memory hypervectors. Optional directory is not a fact store."""

    def __init__(self, *, dim: int = 64, seed: int = 0) -> None:
        self.dim = int(dim)
        self.seed = int(seed)
        self.vectors: dict[str, np.ndarray] = {}
        self.patterns: dict[str, dict[str, Any]] = {}

    def encode(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(f"{self.seed}:{text}".encode("utf-8")).digest()
        rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
        return rng.choice(np.array([-1.0, 1.0]), size=self.dim).astype(np.float64)

    def bind_bundle(self, texts: list[str]) -> np.ndarray:
        vectors = [self.encode(text) for text in texts if str(text).strip()]
        if not vectors:
            return np.zeros(self.dim, dtype=np.float64)
        if len(vectors) == 1:
            return vectors[0]
        bound = vectors[0]
        for vector in vectors[1:]:
            bound = bind(bound, vector)
        return bundle(bound, vectors[0])

    def put(self, key: str, vector: np.ndarray, *, kind: str = "hypervector") -> None:
        self.vectors[str(key)] = np.asarray(vector, dtype=np.float64).ravel()
        if kind == "pattern":
            self.patterns[str(key)] = {"kind": kind, "dim": int(self.vectors[str(key)].size)}

    def get(self, key: str) -> np.ndarray | None:
        vector = self.vectors.get(str(key))
        if vector is None:
            return None
        return np.array(vector, copy=True)

    def nearest(self, vector: np.ndarray, k: int = 3) -> list[dict[str, Any]]:
        query = np.asarray(vector, dtype=np.float64).ravel()
        scored: list[tuple[float, str]] = []
        for key, stored in self.vectors.items():
            if stored.size != query.size:
                continue
            denom = float(np.linalg.norm(stored) * np.linalg.norm(query) + 1e-12)
            scored.append((float(np.dot(stored, query) / denom), key))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [
            {"key": key, "similarity": score, "unverified": True}
            for score, key in scored[: max(0, int(k))]
        ]
