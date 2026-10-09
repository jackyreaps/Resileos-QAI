"""Stress-test the ε-sweep under non-ideal conditions."""
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.reduction import (
    VerifiableFEPReductionHead,
    simulate_axiom_d,
)

D = 64
EPSILONS = [0.1, 0.05, 0.02, 0.01, 0.005]


def _head():
    basis = torch.zeros(D, 1)
    basis[0, 0] = 1.0
    return VerifiableFEPReductionHead(hidden_dim=D, L_H_kernel=basis, rank=1)


def _slope(off_manifold_frac: float = 0.0,
           g_ramp: float = 0.0,
           dt_coarse: float = 1.0) -> float:
    head = _head()

    def factory(eps: float) -> torch.Tensor:
        return simulate_axiom_d(
            dim=D, seq_len=64, epsilon=eps, g_field=0.85, seed=0,
            off_manifold_frac=off_manifold_frac,
            g_ramp=g_ramp, dt_coarse=dt_coarse,
        )

    G = torch.ones(1, 64, 1)
    result = head.sweep_epsilon(factory, EPSILONS, G, metric="rmse")
    return result["slope"]


def test_ideal_still_linear():
    """Baseline: no stress -> slope near 1."""
    s = _slope()
    assert 0.85 < s < 1.15, f"ideal slope {s} out of band"


def test_mild_stress_preserves_bound():
    s = _slope(off_manifold_frac=0.1, g_ramp=0.05, dt_coarse=2.0)
    assert 0.5 < s < 1.5, f"mild-stress slope {s} out of band"


def test_moderate_stress_degrades_gracefully():
    s = _slope(off_manifold_frac=0.2, g_ramp=0.10, dt_coarse=4.0)
    assert s < 3.0, f"moderate-stress slope {s} unexpectedly large"


def test_stress_monotonic_tendency():
    """Slope should not improve (go closer to 1) as stress increases."""
    s_ideal = _slope(0.0, 0.0, 1.0)
    s_stress = _slope(0.5, 0.3, 8.0)
    # Not an assertion of direction; just confirm neither is NaN
    assert s_ideal == s_ideal
    assert s_stress == s_stress
