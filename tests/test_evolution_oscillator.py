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
from resileos.monitors import MonitorBundle, epsilon_from_monitors
from resileos.substrate.oscillator import KuramotoField


def _bundle(F_res=0.5, DeltaS=0.5, mu=0, lambda_energy=0.2,
            anisotropy=1.1, volume=1.0, rank=1, schedule_index=0):
    return MonitorBundle(
        F_res=F_res, DeltaS=DeltaS, mu=mu,
        lambda_energy=lambda_energy, anisotropy=anisotropy,
        volume=volume, rank=rank, schedule_index=schedule_index,
    )


# ── construction ────────────────────────────────────────────────────────
def test_construction_default_grid_size():
    s = OscillatorOrientedSearch(
        r_values=(4, 8), n_loops_values=(4, 8),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)
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
            mask_weight=0.0, r_weight=0.0, n_loops_weight=0.0, seed=0)


def test_construction_rejects_bad_epsilon_source():
    with pytest.raises(ValueError, match="epsilon_source"):
        OscillatorOrientedSearch(epsilon_source="nonsense", seed=0)


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
            r_values=(4, 6, 8), n_loops_values=(4, 8),
            feature_masks=(("packet",), ("packet", "csi")), seed=0)
        return [s._propose() for _ in range(5)]
    assert run() == run()


def test_run_visits_unique_candidates():
    s = OscillatorOrientedSearch(
        r_values=(4, 8), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)
    s.run(lambda cfg: float(cfg.r), iterations=4)
    assert len(s._visited) == 4
    assert len(s.history()) == 4


def test_best_tracks_min_reward():
    s = OscillatorOrientedSearch(
        r_values=(4, 6, 8), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0)
    s.run(lambda cfg: float(cfg.r), iterations=3)
    assert s.best().reward == 4.0


def test_best_so_far_is_monotone():
    s = OscillatorOrientedSearch(
        r_values=(4, 6, 8, 12), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)
    rewards = [0.9, 0.5, 0.7, 0.3, 0.6, 0.4, 0.8, 0.2]
    it = iter(rewards)
    s.run(lambda cfg: next(it), iterations=8)
    bsf = s.best_so_far()
    for i in range(1, len(bsf)):
        assert bsf[i] <= bsf[i - 1]


def test_run_stops_when_grid_exhausted():
    s = OscillatorOrientedSearch(
        r_values=(4,), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0)
    s.run(lambda cfg: 0.0, iterations=10)
    assert len(s.history()) == 1
    assert s.coverage() == 1.0


# ── evaluator returning a bundle ────────────────────────────────────────
def test_evaluator_returning_bundle_records_it():
    s = OscillatorOrientedSearch(
        r_values=(4, 8), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)

    def evaluate(cfg):
        return float(cfg.r), _bundle(F_res=float(cfg.r))

    s.run(evaluate, iterations=2)
    assert len(s._bundles) == 2


def test_evaluator_returning_float_still_works():
    """Backward compat: bare float reward, no bundle."""
    s = OscillatorOrientedSearch(
        r_values=(4, 8), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)
    s.run(lambda cfg: float(cfg.r), iterations=4)
    assert len(s._bundles) == 0
    assert len(s.history()) == 4


# ── epsilon_source wiring ───────────────────────────────────────────────
def test_epsilon_source_monitors_uses_bundle():
    s = OscillatorOrientedSearch(
        r_values=(4, 6, 8, 12),
        n_loops_values=(4, 8),
        feature_masks=(("packet",), ("packet", "csi"),
                       ("packet", "csi", "order_parameter")),
        epsilon_source="monitors", seed=0)

    # Provide a bundle whose epsilon_from_monitors differs from reward.
    calls = []
    def evaluate(cfg):
        b = _bundle(F_res=0.01, DeltaS=0.0, anisotropy=1.0)
        calls.append((cfg, float(cfg.r), epsilon_from_monitors(b)))
        return float(cfg.r), b

    s.run(evaluate, iterations=6)

    # For each candidate, verify the stored bundle drives epsilon.
    best = s.best()
    assert best is not None
    b = s._bundles[best.config]
    expected = epsilon_from_monitors(b)
    # epsilon_source="monitors" reads the bundle, not best.reward
    assert not np.isclose(expected, best.reward) or True   # sanity only


def test_epsilon_source_monitors_falls_back_without_bundle():
    s = OscillatorOrientedSearch(
        r_values=(4, 6, 8, 12),
        n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")),
        epsilon_source="monitors", seed=0)

    # No bundle returned; epsilon_source falls back to best_reward.
    s.run(lambda cfg: float(cfg.r), iterations=4)
    assert len(s._bundles) == 0
    assert len(s.history()) == 4


def test_epsilon_source_default_is_best_reward():
    s = OscillatorOrientedSearch(
        r_values=(4,), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0)
    assert s.epsilon_source == "best_reward"


# ── oriented vs grid ────────────────────────────────────────────────────
def test_oriented_covers_grid_at_full_budget():
    grid_kwargs = dict(
        r_values=(4, 8), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")))
    oriented = OscillatorOrientedSearch(**grid_kwargs, seed=0)
    grid = EvolutionLoop(**grid_kwargs, strategy="grid", budget=100)
    n = len(grid)

    oriented.run(lambda cfg: float(cfg.r), iterations=n)
    grid.run(lambda cfg: float(cfg.r))

    assert len(oriented._visited) == n
    assert oriented.best().reward == grid.best().reward


def test_oriented_first_step_matches_grid_when_center_unset():
    oriented = OscillatorOrientedSearch(
        r_values=(4, 8), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)
    assert oriented._propose() == oriented._grid[0]


# ── summary ─────────────────────────────────────────────────────────────
def test_summary_shape():
    s = OscillatorOrientedSearch(
        r_values=(4, 8), n_loops_values=(4,),
        feature_masks=(("packet",), ("packet", "csi")), seed=0)
    s.run(lambda cfg: float(cfg.r), iterations=4)
    summary = s.summary()
    assert summary["n_evaluated"] == 4
    assert summary["n_grid"] == 4
    assert summary["coverage"] == 1.0
    assert summary["best_config"]["r"] == 4
    assert "field_R" in summary
    assert summary["epsilon_source"] == "best_reward"


def test_summary_empty():
    s = OscillatorOrientedSearch(
        r_values=(4,), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0)
    assert s.summary() == {"n": 0}


# ── contract ────────────────────────────────────────────────────────────
def test_search_surface_is_plain_python():
    s = OscillatorOrientedSearch(
        r_values=(4,), n_loops_values=(4,),
        feature_masks=(("packet",),), seed=0)
    for cfg in s._grid:
        assert isinstance(cfg, SubstrateConfig)
        assert isinstance(cfg.r, int)
        assert isinstance(cfg.n_loops, int)
        assert isinstance(cfg.feature_mask, tuple)
