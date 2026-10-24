"""Incremental factorized views over (s, r, o) facts (F-IVM-inspired).

Design (VLDB F-IVM pattern, adapted to Titanos):
  - Keys are discrete symbols (entity / relation names).
  - Payloads live in a commutative ring (count, mean, covariance stubs).
  - learn_delta / unlearn_delta update only local views — no full attractor
    rebuild, no full band restack.

This does NOT replace Titanos MAP bands or AttractorMemory. It sits beside
them: exact VSA memory for query; incremental rings for analytics under
updates (counts, co-occurrence, online covariance features).

Off states:
  GPU              off
  full IVM engine  off (single-process dict views)
  categorical one-hot expansion  deferred
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import numpy as np


@dataclass
class CountPayload:
    """Trivial (+, *) ring for occurrence counts."""

    n: float = 0.0

    def __add__(self, other: "CountPayload") -> "CountPayload":
        return CountPayload(self.n + other.n)

    def __mul__(self, other: "CountPayload") -> "CountPayload":
        return CountPayload(self.n * other.n)

    def scale(self, c: float) -> "CountPayload":
        return CountPayload(self.n * c)


@dataclass
class CovariancePayload:
    """Running (count, sum, sum-outer) for a small feature vector."""

    dim: int
    n: float = 0.0
    s: Optional[np.ndarray] = None
    Q: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        if self.s is None:
            self.s = np.zeros(self.dim, dtype=np.float64)
        if self.Q is None:
            self.Q = np.zeros((self.dim, self.dim), dtype=np.float64)

    def add_point(self, x: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float64).ravel()
        if x.shape != (self.dim,):
            raise ValueError(f"feature shape {x.shape} != ({self.dim},)")
        self.n += 1.0
        self.s += x
        self.Q += np.outer(x, x)

    def remove_point(self, x: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float64).ravel()
        self.n = max(0.0, self.n - 1.0)
        self.s -= x
        self.Q -= np.outer(x, x)

    def mean(self) -> np.ndarray:
        if self.n <= 0:
            return np.zeros(self.dim, dtype=np.float64)
        return self.s / self.n

    def covariance(self, ddof: int = 1) -> np.ndarray:
        if self.n <= ddof:
            return np.zeros((self.dim, self.dim), dtype=np.float64)
        mean = self.mean()
        return (self.Q - self.n * np.outer(mean, mean)) / (self.n - ddof)


@dataclass
class TripleViews:
    """Factorized incremental views for a triple store."""

    feature_dim: int = 0
    feature_fn: Optional[Callable[[str, str, str], np.ndarray]] = None
    by_relation: dict = field(default_factory=dict)
    by_subject_relation: dict = field(default_factory=dict)
    by_object_relation: dict = field(default_factory=dict)
    cooccur: dict = field(default_factory=dict)
    global_count: CountPayload = field(default_factory=CountPayload)
    cov: Optional[CovariancePayload] = None

    def __post_init__(self) -> None:
        if self.feature_dim > 0 and self.cov is None:
            self.cov = CovariancePayload(dim=self.feature_dim)

    def learn_delta(self, subject: str, relation: str, obj: str) -> None:
        s, r, o = str(subject), str(relation), str(obj)
        self.global_count.n += 1.0
        self.by_relation[r] = self.by_relation.get(r, 0.0) + 1.0
        sr = (s, r)
        self.by_subject_relation[sr] = self.by_subject_relation.get(sr, 0.0) + 1.0
        or_ = (o, r)
        self.by_object_relation[or_] = self.by_object_relation.get(or_, 0.0) + 1.0
        a, b = (s, o) if s <= o else (o, s)
        if a != b:
            self.cooccur[(a, b)] = self.cooccur.get((a, b), 0.0) + 1.0
        if self.cov is not None and self.feature_fn is not None:
            self.cov.add_point(self.feature_fn(s, r, o))

    def unlearn_delta(self, subject: str, relation: str, obj: str) -> None:
        s, r, o = str(subject), str(relation), str(obj)
        self.global_count.n = max(0.0, self.global_count.n - 1.0)
        self.by_relation[r] = max(0.0, self.by_relation.get(r, 0.0) - 1.0)
        sr = (s, r)
        self.by_subject_relation[sr] = max(
            0.0, self.by_subject_relation.get(sr, 0.0) - 1.0
        )
        or_ = (o, r)
        self.by_object_relation[or_] = max(
            0.0, self.by_object_relation.get(or_, 0.0) - 1.0
        )
        a, b = (s, o) if s <= o else (o, s)
        if a != b and (a, b) in self.cooccur:
            self.cooccur[(a, b)] = max(0.0, self.cooccur[(a, b)] - 1.0)
        if self.cov is not None and self.feature_fn is not None:
            self.cov.remove_point(self.feature_fn(s, r, o))

    def learn_many(self, triples: Iterable[tuple[str, str, str]]) -> int:
        n = 0
        for s, r, o in triples:
            self.learn_delta(s, r, o)
            n += 1
        return n

    def n_objects(self, subject: str, relation: str) -> float:
        return float(self.by_subject_relation.get((str(subject), str(relation)), 0.0))

    def relation_mass(self, relation: str) -> float:
        return float(self.by_relation.get(str(relation), 0.0))

    def top_relations(self, k: int = 10) -> list[tuple[str, float]]:
        items = sorted(self.by_relation.items(), key=lambda x: -x[1])
        return items[:k]

    def top_cooccur(self, k: int = 10) -> list[tuple[tuple[str, str], float]]:
        items = sorted(self.cooccur.items(), key=lambda x: -x[1])
        return items[:k]

    def snapshot(self) -> dict:
        return {
            "global_count": self.global_count.n,
            "n_relations": len(self.by_relation),
            "n_sr_keys": len(self.by_subject_relation),
            "n_cooccur": len(self.cooccur),
            "top_relations": self.top_relations(5),
            "has_covariance": self.cov is not None and self.cov.n > 0,
            "cov_n": None if self.cov is None else self.cov.n,
        }


def hashed_triple_features(dim: int, seed: int = 0):
    """Return feature_fn(s, r, o) -> (dim,) ±1 bag-of-hash features."""

    def _h(token: str) -> np.ndarray:
        h = (hash((seed, token)) % (2**31)) / (2**31)
        local = np.random.default_rng(int(h * 1e9) ^ seed)
        return local.choice([-1.0, 1.0], size=dim)

    def feature_fn(s: str, r: str, o: str) -> np.ndarray:
        return _h(s) + _h(r) + _h(o)

    return feature_fn


__all__ = [
    "CountPayload",
    "CovariancePayload",
    "TripleViews",
    "hashed_triple_features",
]
