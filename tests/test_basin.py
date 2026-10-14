"""Tests for basin metrics, sheath detection, and MaxCut helpers."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.basin import (
    BasinConfig,
    basin_volume,
    basin_depth,
    basin_entropy,
    boundary_codimension,
    measure_basin,
)
from resileos.substrate.sheath import SheathConfig, sheath_metrics
from resileos.substrate.maxcut import (
    MaxCutInstance,
    random_maxcut,
    random_partition,
    local_search,
    simulated_annealing,
)


def test_maxcut_cut_value_trivial():
    A = np.array([[0, 1], [1, 0]])
    inst = MaxCutInstance(n=2, adjacency=A)
    assert inst.cut_value(np.array([1, -1])) == 1
    assert inst.cut_value(np.array([1, 1])) == 0


def test_random_maxcut_symmetric():
    inst = random_maxcut(8, seed=0)
    assert np.array_equal(inst.adjacency, inst.adjacency.T)
    assert np.all(np.diag(inst.adjacency) == 0)


def test_local_search_improves_or_equal():
    inst = random_maxcut(10, seed=0)
    rng = np.random.default_rng(0)
    init = random_partition(10, rng)
    before = inst.cut_value(init)
    after = inst.cut_value(local_search(inst, init))
    assert after >= before


def test_anneal_runs():
    inst = random_maxcut(8, seed=0)
    rng = np.random.default_rng(0)
    init = random_partition(8, rng)
    final = simulated_annealing(inst, init, steps=100, seed=0)
    assert final.shape == (8,)
    assert set(np.unique(final)).issubset({-1.0, 1.0})


def test_basin_volume_all_one_mode():
    def step_fn(x):
        return 7
    cfg = BasinConfig(n_states=20, n_dims=4, seed=0)
    v, counts = basin_volume(step_fn, target_mode=7, cfg=cfg)
    assert v == 1.0
    assert counts == {7: 20}


def test_basin_volume_disjoint_modes():
    def step_fn(x):
        return 0 if x[0] >= 0 else 1
    cfg = BasinConfig(n_states=200, n_dims=2, seed=0)
    v0, counts = basin_volume(step_fn, target_mode=0, cfg=cfg)
    assert 0.4 < v0 < 0.6
    assert 0 in counts and 1 in counts


def test_basin_depth_random_directions():
    def step_fn(x):
        return 0
    cfg = BasinConfig(n_dims=3, seed=0)
    d = basin_depth(step_fn, np.zeros(3), target_mode=0, cfg=cfg)
    assert d > 0.0


def test_basin_depth_structured_directions():
    def step_fn(x):
        return 0
    cfg = BasinConfig(n_dims=3, seed=0)
    dirs = np.eye(3)
    d = basin_depth(step_fn, np.zeros(3), target_mode=0, cfg=cfg,
                    directions=dirs)
    assert d > 0.0


def test_basin_entropy_single_mode():
    assert basin_entropy({0: 100}) == pytest.approx(1.0)


def test_basin_entropy_uniform_two():
    e = basin_entropy({0: 50, 1: 50})
    assert e == pytest.approx(2.0, abs=1e-6)


def test_boundary_codimension_flat():
    # step_fn constant -> no boundary -> P(straddle) = 0 -> codim huge
    def step_fn(x):
        return 0
    cfg = BasinConfig(n_dims=4, codim_pairs=50, seed=0)
    codim = boundary_codimension(step_fn, cfg)
    assert codim > 1.0


def test_boundary_codimension_halfspace():
    # boundary at x[0] = 0 -> codimension ~ 1
    def step_fn(x):
        return 0 if x[0] >= 0 else 1
    cfg = BasinConfig(n_dims=4, codim_pairs=300, seed=0)
    codim = boundary_codimension(step_fn, cfg)
    assert 0.5 < codim < 1.5


def test_sheath_metrics_constraint_regime():
    def step_fn(x):
        return 0 if x[0] >= 0 else 1
    cfg = BasinConfig(n_states=100, n_dims=4, boundary_grid=16,
                      codim_pairs=100, hop_duration=20, seed=0)
    m = sheath_metrics(step_fn, target_mode=0, cfg=cfg)
    assert m["regime"] in ("constraint", "saturated-boundary", "wall",
                           "sheath")
    assert "boundary_codim" in m
    assert "basin_entropy" in m


def test_sheath_metrics_returns_all_keys():
    def step_fn(x):
        return 0
    cfg = BasinConfig(n_states=50, n_dims=4, boundary_grid=16,
                      codim_pairs=50, hop_duration=20, seed=0)
    m = sheath_metrics(step_fn, target_mode=0, cfg=cfg)
    for k in ("n", "volume", "depth", "boundary_dim", "boundary_codim",
              "norm_boundary_dim", "hopping_rate", "basin_entropy",
              "saturated", "collapsed", "is_sheath", "regime"):
        assert k in m


def test_measure_basin_returns_all_fields():
    def step_fn(x):
        return int(np.sum(x) > 0)
    cfg = BasinConfig(n_states=50, n_dims=4, boundary_grid=16,
                      codim_pairs=50, hop_duration=20, seed=0)
    res = measure_basin(step_fn, target_mode=0, cfg=cfg)
    d = res.to_dict()
    for k in ("volume", "depth", "boundary_dim", "hopping_rate",
              "n_used", "mode_counts", "boundary_codim", "basin_entropy"):
        assert k in d
