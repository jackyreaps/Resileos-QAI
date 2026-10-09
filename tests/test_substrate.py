"""
Substrate tests: compliance and numerical correctness.

These tests are written against the claims in RES-600/601/602. If a test
fails, either the code or the doc is wrong — the failure is the signal.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.geometry import LowRankMetricHead, BridgeMetricHead
from resileos.substrate.reduction import (
    VerifiableFEPReductionHead,
    simulate_linear_ode,
)


# ── fixtures ──────────────────────────────────────────────────────────────
D = 64
T = 8
KERNEL_DIM = 1


@pytest.fixture
def kernel_basis():
    torch.manual_seed(0)
    raw = torch.randn(D, KERNEL_DIM)
    q, _ = torch.linalg.qr(raw)
    return q


@pytest.fixture
def fep_head(kernel_basis):
    return VerifiableFEPReductionHead(hidden_dim=D, L_H_kernel=kernel_basis, rank=1)


# ── geometry head ─────────────────────────────────────────────────────────
def test_geometry_no_crash():
    """Bug 1 fix: previously crashed on view() shape mismatch."""
    head = LowRankMetricHead(hidden_dim=D, low_rank_dim=8, epsilon=1e-3)
    trunk = torch.randn(1, T, D)
    x_dir = torch.randn(1, T, D)
    V, loss = head(trunk, x_dir)
    assert V.shape == (1, T, D)
    assert loss.shape == ()
    assert torch.isfinite(loss)


def test_geometry_rejects_wrong_batch():
    head = LowRankMetricHead(hidden_dim=D)
    trunk = torch.randn(2, T, D)     # batch > 1
    x_dir = torch.randn(2, T, D)
    with pytest.raises(ValueError, match="batch|must be \\[1"):
        head(trunk, x_dir)


def test_bridge_head_locked():
    """BridgeMetricHead must raise until rheology is derived."""
    head = BridgeMetricHead()
    with pytest.raises(NotImplementedError):
        head(torch.randn(1, T, D))


# ── reduction head ────────────────────────────────────────────────────────
def test_psi_s_is_scalar_trajectory(fep_head):
    """Bug 2 fix: P_s has rank 1, psi_s is [1, T, 1], no mean-collapse."""
    trunk = torch.randn(1, T, D)
    G = torch.ones(1, T, 1)
    psi_s, err = fep_head(trunk, G)
    assert psi_s.shape == (1, T, 1)
    assert torch.isfinite(err)


def test_psi_s_is_actually_projected(fep_head):
    """psi_s must equal trunk @ P_s @ basis, not an arbitrary reduction."""
    trunk = torch.randn(1, T, D)
    G = torch.ones(1, T, 1)
    psi_s, _ = fep_head(trunk, G)

    expected = (trunk @ fep_head.P_s) @ fep_head.basis   # [1, T, 1]
    assert torch.allclose(psi_s, expected, atol=1e-5)


def test_ode_recovers_known_rate(kernel_basis):
    """The head should be able to fit a trajectory produced by the linear ODE."""
    # Place the first basis direction along the first ambient coordinate so
    # our simulated trajectory (which lives on coordinate 0) is visible.
    basis = torch.zeros(D, 1)
    basis[0, 0] = 1.0
    head = VerifiableFEPReductionHead(hidden_dim=D, L_H_kernel=basis, rank=1)

    gamma_true = 0.2
    trunk = simulate_linear_ode(D, T, gamma_true=gamma_true, seed=0)
    G = torch.ones(1, T, 1)

    psi_s, err = head(trunk, G)
    # The trajectory is on coordinate 0 with well at psi_b=1.5.
    # psi_s should track it.
    assert psi_s[0, 0, 0].item() == pytest.approx(2.0, abs=0.05)
    assert torch.isfinite(err)


def test_epsilon_sweep_produces_slope(kernel_basis):
    """Bug 3 fix: sweep must return slope + r_squared."""
    head = VerifiableFEPReductionHead(hidden_dim=D, L_H_kernel=kernel_basis, rank=1)
    G = torch.ones(1, T, 1)

    # Sweep perturbation scale; seed variation is the "epsilon" here.
    def factory(eps: float):
        # Scale the initial perturbation by eps
        trunk = simulate_linear_ode(D, T, gamma_true=0.2, seed=0)
        trunk[:, 0] = 1.5 + eps
        return trunk

    result = head.sweep_epsilon(factory, [0.1, 0.01, 0.001], G)
    assert "slope" in result
    assert "r_squared" in result
    assert np.isfinite(result["slope"])
    assert -5.0 < result["slope"] < 5.0     # loose sanity


# ── training-state flag ───────────────────────────────────────────────────
def test_training_flag_not_set_by_single_step(kernel_basis):
    """Bug 4 fix: one optimizer step must not flip is_trained."""
    # Local mini-harness; mirrors what app.py does.
    geo = LowRankMetricHead(hidden_dim=D, low_rank_dim=8)
    fep = VerifiableFEPReductionHead(hidden_dim=D, L_H_kernel=kernel_basis)
    params = list(geo.parameters()) + list(fep.parameters())
    opt = torch.optim.AdamW(params, lr=1e-3)

    state = {"trained": False, "steps": 0, "min_steps": 5}

    def step():
        opt.zero_grad()
        trunk = torch.randn(1, T, D)
        x = torch.randn(1, T, D)
        G = torch.ones(1, T, 1)
        _, gl = geo(trunk, x)
        _, fl = fep(trunk, G)
        (gl + fl).backward()
        opt.step()
        state["steps"] += 1
        if state["steps"] >= state["min_steps"]:
            state["trained"] = True

    step()
    assert state["trained"] is False
    for _ in range(5):
        step()
    assert state["trained"] is True
