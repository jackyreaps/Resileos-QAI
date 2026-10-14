"""Tests for outer-loop substrate evolution."""
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.evolution import (
    SubstrateConfig, EvolutionRecord, EvolutionLoop,
)


# ── config validation ───────────────────────────────────────────────────
def test_config_valid():
    cfg = SubstrateConfig(r=8, n_loops=12, feature_mask=("packet",))
    assert cfg.r == 8
    assert cfg.n_loops == 12
    assert cfg.feature_mask == ("packet",)


def test_config_rejects_bad_r():
    with pytest.raises(ValueError, match="r"):
        SubstrateConfig(r=0, n_loops=4, feature_mask=("packet",))


def test_config_rejects_bad_loops():
    with pytest.raises(ValueError, match="n_loops"):
        SubstrateConfig(r=4, n_loops=0, feature_mask=("packet",))


def test_config_rejects_unknown_feature():
    with pytest.raises(ValueError, match="unknown feature"):
        SubstrateConfig(r=4, n_loops=4, feature_mask=("packet", "nonsense"))


def test_config_requires_packet():
    with pytest.raises(ValueError, match="packet"):
        SubstrateConfig(r=4, n_loops=4, feature_mask=("csi",))


def test_config_is_hashable():
    a = SubstrateConfig(r=4, n_loops=4, feature_mask=("packet",))
    b = SubstrateConfig(r=4, n_loops=4, feature_mask=("packet",))
    assert a == b
    assert hash(a) == hash(b)
    assert {a, b} == {a}


# ── loop construction ───────────────────────────────────────────────────
def test_grid_candidates_exhaustive():
    loop = EvolutionLoop(
        r_values=(4, 8),
        n_loops_values=(4, 8),
        feature_masks=(("packet",), ("packet", "csi")),
        strategy="grid",
        budget=100,
    )
    assert len(loop) == 2 * 2 * 2


def test_random_candidates_budget():
    loop = EvolutionLoop(
        r_values=(4, 6, 8),
        n_loops_values=(4, 8, 12),
        feature_masks=(
            ("packet",),
            ("packet", "csi"),
            ("packet", "csi", "order_parameter"),
        ),
        strategy="random",
        budget=7,
        seed=0,
    )
    assert len(loop) == 7


def test_random_candidates_deduped():
    loop = EvolutionLoop(
        r_values=(4,),
        n_loops_values=(4,),
        feature_masks=(("packet",),),
        strategy="random",
        budget=10,
        seed=0,
    )
    # Only one distinct config exists; the budget cannot be exceeded.
    assert len(loop) == 1


def test_unknown_strategy_raises():
    with pytest.raises(ValueError, match="strategy"):
        EvolutionLoop(strategy="nonsense")


# ── observe / best / history ────────────────────────────────────────────
def test_observe_records():
    loop = EvolutionLoop(
        r_values=(4, 8), n_loops_values=(4,), feature_masks=(("packet",),),
        strategy="grid", budget=10,
    )
    cfgs = list(loop)
    loop.observe(cfgs[0], 0.5)
    loop.observe(cfgs[1], 0.3)
    assert len(loop.history()) == 2
    best = loop.best()
    assert best.reward == 0.3
    assert best.config == cfgs[1]


def test_best_empty_is_none():
    loop = EvolutionLoop(strategy="grid", budget=10)
    assert loop.best() is None


def test_ranked_ordering():
    loop = EvolutionLoop(
        r_values=(4, 8), n_loops_values=(4,), feature_masks=(("packet",),),
        strategy="grid", budget=10,
    )
    cfgs = list(loop)
    loop.observe(cfgs[0], 0.9)
    loop.observe(cfgs[1], 0.1)
    ranked = loop.ranked()
    assert [r.reward for r in ranked] == [0.1, 0.9]


# ── run with a callable ─────────────────────────────────────────────────
def test_run_evaluates_all_candidates():
    loop = EvolutionLoop(
        r_values=(4, 8), n_loops_values=(4,), feature_masks=(("packet",),),
        strategy="grid", budget=10,
    )
    called = []
    def evaluator(cfg):
        called.append(cfg)
        return float(cfg.r)
    loop.run(evaluator)
    assert len(called) == len(loop)
    assert loop.best().reward == 4.0


def test_run_metadata_passthrough():
    loop = EvolutionLoop(
        r_values=(4,), n_loops_values=(4,), feature_masks=(("packet",),),
        strategy="grid", budget=10,
    )
    loop.run(lambda cfg: 0.0, tag="v1")
    assert loop.history()[0].metadata.get("tag") == "v1"


# ── determinism ─────────────────────────────────────────────────────────
def test_random_strategy_deterministic():
    def build():
        return EvolutionLoop(
            r_values=(4, 6, 8),
            n_loops_values=(4, 8, 12),
            feature_masks=(("packet",), ("packet", "csi")),
            strategy="random",
            budget=8,
            seed=42,
        )
    a = list(build())
    b = list(build())
    assert a == b


def test_random_strategy_seed_sensitive():
    a = list(EvolutionLoop(
        r_values=(4, 6, 8, 12),
        n_loops_values=(4, 8, 12),
        feature_masks=(("packet",), ("packet", "csi")),
        strategy="random", budget=5, seed=1,
    ))
    b = list(EvolutionLoop(
        r_values=(4, 6, 8, 12),
        n_loops_values=(4, 8, 12),
        feature_masks=(("packet",), ("packet", "csi")),
        strategy="random", budget=5, seed=2,
    ))
    assert a != b


# ── summary ─────────────────────────────────────────────────────────────
def test_summary_shape():
    loop = EvolutionLoop(
        r_values=(4, 8), n_loops_values=(4,), feature_masks=(("packet",),),
        strategy="grid", budget=10,
    )
    loop.run(lambda cfg: float(cfg.r))
    s = loop.summary()
    assert s["n_evaluated"] == 2
    assert s["reward_min"] == 4.0
    assert s["reward_max"] == 8.0
    assert s["best_config"]["r"] == 4
    assert s["best_config"]["n_loops"] == 4
    assert s["best_config"]["feature_mask"] == ["packet"]


def test_summary_empty():
    loop = EvolutionLoop(strategy="grid", budget=10)
    assert loop.summary() == {"n": 0}


# ── contract: no gradient into substrate ────────────────────────────────
def test_evolution_does_not_touch_substrate_parameters():
    loop = EvolutionLoop(
        r_values=(4,), n_loops_values=(4,), feature_masks=(("packet",),),
        strategy="grid", budget=1,
    )
    for cfg in loop:
        assert isinstance(cfg, SubstrateConfig)
        assert not isinstance(cfg.r, torch.Tensor)
        assert not isinstance(cfg.n_loops, torch.Tensor)
