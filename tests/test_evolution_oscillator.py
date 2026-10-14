"""Tests for oscillator-oriented discrete grid search."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.evolution import EvolutionLoop, SubstrateConfig
from resileos.evolution_oscillator import (
    OscillatorOrientedSearch, MASK_BITS,
)
from resileos.substrate.oscillator import KuramotoField


# ── construction ────────────────────────────────────────────────────────
def test_construction_default_grid_size():
    s = OscillatorOrientedSearch(
        r_values=(4, 8),
        n_loops_values=(4, 8),
        feature_masks=(("packet",), ("packet", "csi")),
        seed=0,
    )
    assert len(s._grid) == 2 * 2 * 2


def test_construction_rejects_empty_r():
    with pytest.raises(ValueError, match="empty search space"):
        OscillatorOrientedSearch(r_values=(), seed=0)


def test_construction_rejects_bad_field_size():
    field = KuramotoField(r=5, random_start=True, seed=0)
    with pytest.raises(ValueError, match="3 oscillators"):
        OscillatorOrientedSearch(field=field, seed=0)


def test_construction_rejects_zero_weights():
    with pytest.raises(ValueError, match="weights"):
        OscillatorOrientedSearch(
            mask_weight=0.0, r_weight=0.0, n_loops_weight=0.0, seed=0,
        )


# ── bit helpers ─────────────────────────────────────────────────────────
def test_mask_to_bits_all_off():
    bits = OscillatorOrientedSearch._mask_to_bits(("packet",))
    assert np.allclose(bits, 0.0)


def test_mask_to_bits_all_on():
    bits = OscillatorOrientedSearch._mask_to_bits(
        ("packet",) + tuple(MASK_BITS))
    assert np.allclose(bits, 1.0)


def test_bits_to_mask_roundtrip():
    for m in [("packet",),
              ("packet", "csi"),
              ("packet", "csi", "direction"),
              ("packet",) + tuple(MASK_BITS)]:
        bits = OscillatorOrientedSearch._mask_to_bits(m)
        assert OscillatorOrientedSearch._bits_to_mask(bits) == m


# ── search behavior ─────────────────────────────────────────────────────
def test_propose_is_deterministic():
    def run():
        s = OscillatorOrientedSearch(
            r_values=(4, 6, 8),
            n_loops_values=(4, 8),
            feature_masks=(("packet",), ("packet", "csi")),
            seed=0,
        )
        return [s._propose() for _ in range(5)]
    assert run() == run()


def test_run_visits_unique_candidates():
    s = OscillatorOrientedSearch(
        r_values=(4, 8),
        n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")),
        seed=0,
    )
    s.run(lambda cfg: float(cfg.r), iterations=4)
    assert len(s._visited) == 4
    assert len(s.history()) == 4


def test_best_tracks_min_reward():
    s = OscillatorOrientedSearch(
        r_values=(4, 6, 8),
        n_loops_values=(4,),
        feature_masks=(("packet",),),
        seed=0,
    )
    s.run(lambda cfg: float(cfg.r), iterations=3)
    assert s.best().reward == 4.0


def test_best_so_far_is_monotone():
    s = OscillatorOrientedSearch(
        r_values=(4, 6, 8, 12),
        n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")),
        seed=0,
    )
    rewards = [0.9, 0.5, 0.7, 0.3, 0.6, 0.4, 0.8, 0.2]
    it = iter(rewards)
    s.run(lambda cfg: next(it), iterations=8)
    bsf = s.best_so_far()
    for i in range(1, len(bsf)):
        assert bsf[i] <= bsf[i - 1]


def test_run_stops_when_grid_exhausted():
    s = OscillatorOrientedSearch(
        r_values=(4,),
        n_loops_values=(4,),
        feature_masks=(("packet",),),
        seed=0,
    )
    s.run(lambda cfg: 0.0, iterations=10)
    assert len(s.history()) == 1
    assert s.coverage() == 1.0


# ── orientation: theta influences proposal ─────────────────────────────
def test_stronger_coupling_reduces_distance_from_center():
    """
    Two searches, same first candidate. A field with high kappa
    (strong coupling -> high R) should propose a candidate closer to
    the center than a field with kappa = 0 (no coupling -> low R).
    """
    def make(kappa: float):
        return OscillatorOrientedSearch(
            r_values=(4, 6, 8, 12),
            n_loops_values=(4, 8),
            feature_masks=(("packet",), ("packet", "csi"),
                           ("packet", "csi", "order_parameter")),
            kappa=kappa,
            seed=0,
        )

    strong = make(kappa=20.0)
    weak = make(kappa=0.0)

    # Evaluate the first proposal for each so _center is set.
    c0 = strong._propose()
    strong._visited.add(c0)
    from resileos.evolution import EvolutionRecord
    strong._history.append(EvolutionRecord(c0, 0.3))

    c0w = weak._propose()
    weak._visited.add(c0w)
    weak._history.append(EvolutionRecord(c0w, 0.3))

    # Advance the fields many steps so R settles.
    for _ in range(200):
        strong.field.step(epsilon=0.3, W=strong.W)
    for _ in range(200):
        weak.field.step(epsilon=0.3, W=weak.W)

    R_strong = strong.field.order_parameter()
    R_weak = weak.field.order_parameter()
    assert R_strong > R_weak, f"R_strong={R_strong}, R_weak={R_weak}"


# ── A/B against EvolutionLoop ──────────────────────────────────────────
def test_oriented_covers_grid_at_full_budget():
    """With a full-grid budget, both searchers visit every candidate."""
    grid_kwargs = dict(
        r_values=(4, 8),
        n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")),
    )
    oriented = OscillatorOrientedSearch(**grid_kwargs, seed=0)
    grid = EvolutionLoop(**grid_kwargs, strategy="grid", budget=100)
    n = len(grid)

    oriented.run(lambda cfg: float(cfg.r), iterations=n)
    grid.run(lambda cfg: float(cfg.r))

    assert len(oriented._visited) == n
    assert oriented.best().reward == grid.best().reward


def test_oriented_first_step_matches_grid_when_center_unset():
    """Before any evaluation, the first proposal is unvisited[0]."""
    oriented = OscillatorOrientedSearch(
        r_values=(4, 8),
        n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")),
        seed=0,
    )
    first = oriented._propose()
    assert first == oriented._grid[0]


# ── summary ─────────────────────────────────────────────────────────────
def test_summary_shape():
    s = OscillatorOrientedSearch(
        r_values=(4, 8),
        n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")),
        seed=0,
    )
    s.run(lambda cfg: float(cfg.r), iterations=4)
    summary = s.summary()
    assert summary["n_evaluated"] == 4
    assert summary["n_grid"] == 4
    assert summary["coverage"] == 1.0
    assert summary["best_config"]["r"] == 4
    assert "field_R" in summary


def test_summary_empty():
    s = OscillatorOrientedSearch(
        r_values=(4,), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0,
    )
    assert s.summary() == {"n": 0}


# ── contract: no gradient into substrate ───────────────────────────────
def test_search_surface_is_plain_python():
    s = OscillatorOrientedSearch(
        r_values=(4,), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0,
    )
    for cfg in s._grid:
        assert isinstance(cfg, SubstrateConfig)
        assert isinstance(cfg.r, int)
        assert isinstance(cfg.n_loops, int)
        assert isinstance(cfg.feature_mask, tuple)
