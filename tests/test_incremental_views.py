"""Tests for F-IVM-inspired incremental triple views."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.incremental_views import (
    CovariancePayload,
    TripleViews,
    hashed_triple_features,
)


def test_learn_delta_counts():
    v = TripleViews()
    v.learn_delta("Zeus", "parent_of", "Ares")
    v.learn_delta("Zeus", "parent_of", "Athena")
    assert v.global_count.n == 2
    assert v.n_objects("Zeus", "parent_of") == 2
    assert v.relation_mass("parent_of") == 2


def test_unlearn_delta():
    v = TripleViews()
    v.learn_delta("a", "r", "b")
    v.unlearn_delta("a", "r", "b")
    assert v.global_count.n == 0
    assert v.n_objects("a", "r") == 0


def test_learn_many_and_cooccur():
    v = TripleViews()
    n = v.learn_many([("a", "r", "b"), ("a", "r", "c"), ("b", "r2", "c")])
    assert n == 3
    assert v.cooccur[("a", "b")] >= 1


def test_covariance_ring():
    dim = 8
    cov = CovariancePayload(dim=dim)
    rng = np.random.default_rng(0)
    for _ in range(50):
        cov.add_point(rng.normal(size=dim))
    C = cov.covariance()
    assert C.shape == (dim, dim)
    assert cov.n == 50


def test_hashed_features_views():
    dim = 16
    fn = hashed_triple_features(dim, seed=1)
    v = TripleViews(feature_dim=dim, feature_fn=fn)
    v.learn_many([("x", "rel", "y"), ("x", "rel", "z")])
    assert v.cov is not None and v.cov.n == 2
    snap = v.snapshot()
    assert snap["global_count"] == 2
