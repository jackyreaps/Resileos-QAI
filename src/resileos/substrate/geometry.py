""" Head 1: geometric manifold tracking.

SPECIFICATION COMPLIANCE STATUS:
    LowRankMetricHead — STRUCTURAL PROXY SUBSTITUTE (see RES-602 §3).
        Uses g = L Lᵀ + εI, not the RES-601 §7 bridge. Requires explicit
        labelling per RES-602 §5.4.
    BridgeMetricHead — CANONICAL METRIC BRIDGE (RES-601 §7). Locked until
        rheology coordinates x are derived. Raises NotImplementedError.
    CandidateBridgeMetricHead — RES-606 §5 conformal candidate. Separate from
        the locked canonical bridge. Used for evaluation only. No directional
        content in the scalar-M regime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import torch
import torch.nn as nn


class LowRankMetricHead(nn.Module):
    """SPECIFICATION COMPLIANCE STATUS: STRUCTURAL PROXY SUBSTITUTE.

    Implements g = L Lᵀ + εI where L_t = trunk_state_t · W_L, projected per
    time step. This is NOT the canonical metric bridge of RES-601 §7.

    Provides covariant parallel transport penalty ||∇_X V||² via Woodbury
    inverse on the low-rank metric:
        g⁻¹ = (1/ε)(I − L(LᵀL + εI_r)⁻¹Lᵀ)

    Inputs:
        trunk_state [1, T, D]   temporal trajectory tensors
        X_direction [1, T, D]   directional velocity field
    Returns:
        V_seq [1, T, D]         intentionality vectors
        loss  scalar            mean ||∇_X V||²
    """

    def __init__(self, hidden_dim: int, low_rank_dim: int = 32, epsilon: float = 1e-3):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.low_rank_dim = low_rank_dim
        self.epsilon = epsilon
        self.W_L = nn.Parameter(torch.randn(hidden_dim, low_rank_dim) / (hidden_dim ** 0.5))
        self.W_V = nn.Parameter(torch.randn(hidden_dim, hidden_dim) / (hidden_dim ** 0.5))

    def forward(self, trunk_state: torch.Tensor, X_direction: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if trunk_state.dim() != 3 or trunk_state.size(0) != 1:
            raise ValueError(f"trunk_state must be [1, T, D], got {tuple(trunk_state.shape)}")
        if X_direction.shape != trunk_state.shape:
            raise ValueError(f"X_direction {tuple(X_direction.shape)} must match trunk_state {tuple(trunk_state.shape)}")
        B, T, D = trunk_state.shape
        if D != self.hidden_dim:
            raise ValueError(f"hidden_dim {self.hidden_dim} != trunk last dim {D}")
        r = self.low_rank_dim
        eps = self.epsilon
        L_seq = torch.einsum("td,dr->tdr", trunk_state.squeeze(0), self.W_L)
        V_seq = trunk_state.squeeze(0) @ self.W_V
        X_seq = X_direction.squeeze(0)
        eye_r = torch.eye(r, device=trunk_state.device, dtype=trunk_state.dtype)
        loss_sum = trunk_state.new_zeros(())
        for t in range(T):
            L = L_seq[t]
            V = V_seq[t]
            X = X_seq[t]
            LtL = L.transpose(0, 1) @ L
            reg_inv = torch.inverse(LtL + eps * eye_r)

            def g_inv(vec: torch.Tensor) -> torch.Tensor:
                Lt_vec = L.transpose(0, 1) @ vec
                sub = reg_inv @ Lt_vec
                return (vec - L @ sub) / eps

            partial_V_X = self.W_V @ X
            W_L_X = self.W_L.transpose(0, 1) @ X
            W_L_V = self.W_L.transpose(0, 1) @ V
            L_X = L.transpose(0, 1) @ X
            L_V = L.transpose(0, 1) @ V
            term_1 = (L @ W_L_V) * X + (L @ W_L_X) * V
            term_2 = self.W_L @ (L_V * W_L_X)
            christoffel_V_X = 0.5 * g_inv(term_1 + term_2)
            nabla_X_V = partial_V_X + christoffel_V_X
            loss_sum = loss_sum + torch.sum(nabla_X_V ** 2)
        return V_seq.unsqueeze(0), loss_sum / T


class BridgeMetricHead(nn.Module):
    """SPECIFICATION COMPLIANCE STATUS: CANONICAL METRIC BRIDGE (RES-601 §7).

    Implements:
        g_ij(x) = δ_ij · 1/(1 + Re_ε(x)) + (G(x)/(Ψ_B − Ψ_A)) · M_E^(ij)

    LOCKED: requires the rheology coordinate system x, which is currently
    underived (Non_dual_adaptation.md §7 lists three open items). Until the
    coordinate system, Re_ε dependence, and positive-definiteness are
    established, this head raises NotImplementedError by design.
    """

    def __init__(self) -> None:
        super().__init__()
        self.is_derivable = False

    def forward(self, x: torch.Tensor):
        raise NotImplementedError(
            "Canonical bridge is structurally locked. Requires: "
            "(1) explicit rheology coordinates x; "
            "(2) Re_ε and G dependence derivation; "
            "(3) positive-definiteness verification. "
            "See RES-601 §7 for the three open items."
        )


# ── RES-606 §5 candidate ────────────────────────────────────────────────

@dataclass(frozen=True)
class CandidateScalars:
    Re: float
    G: float
    m0: float
    c: float


class CandidateBridgeMetricHead(nn.Module):
    """RES-606 §5 conformal candidate for the RES-601 §7 metric.

    Separate from the locked BridgeMetricHead. Used for evaluation only.
    Implements:
        c(x) = 1/(1+Re(x)) + G(x) · m0 / (φ_B − φ_A)
        g_ij = c(x) · δ_ij

    No directional content in the scalar-M regime. This class does not
    unlock BridgeMetricHead. It instantiates the candidate algebra so it
    can be tested for SPD and compared against LowRankMetricHead on real
    monitors.

    Parameters
    ----------
    p, tau, k : scalars for the Re(x) derivation. See RES-606 §2.
    g0, g_ramp : coherence schedule parameters. See RES-606 §3.
    phi_A, phi_B : well positions. Defaults match the FEP head.
    """

    def __init__(
        self,
        p: int = 4,
        tau: float = 1.0 / 512.0,
        k: float = 1.0 / 64.0,
        g0: float = 0.85,
        g_ramp: float = 0.0,
        phi_A: float = 0.5,
        phi_B: float = 1.5,
    ) -> None:
        super().__init__()
        if p <= 0:
            raise ValueError("p must be > 0")
        if tau <= 0 or k <= 0:
            raise ValueError("tau and k must be > 0")
        if phi_B <= phi_A:
            raise ValueError("phi_B must be > phi_A")
        self.p = int(p)
        self.tau = float(tau)
        self.k = float(k)
        self.g0 = float(g0)
        self.g_ramp = float(g_ramp)
        self.phi_A = float(phi_A)
        self.phi_B = float(phi_B)

        from ..packet import EPS
        self.L = float(EPS) ** (1.0 / self.p)
        self.v = self.k * self.L * self.L / self.tau
        self.m0 = self.phi_B / (self.phi_B - self.phi_A)
        self.re_coefficient = self.tau / (self.k * self.L)

    def Re(self, F_res: float) -> float:
        return abs(float(F_res)) * self.re_coefficient

    def G(self, t: int, T: int) -> float:
        if T <= 1:
            return self.g0
        return self.g0 * (1.0 + self.g_ramp * t / float(T - 1))

    @staticmethod
    def _get(monitors: Any, key: str) -> float:
        if isinstance(monitors, dict):
            return float(monitors[key])
        return float(getattr(monitors, key))

    def evaluate(self, monitors: Any, t: int, T: int) -> CandidateScalars:
        F_res = self._get(monitors, "F_res")
        re_val = self.Re(F_res)
        g_val = self.G(t, T)
        c = 1.0 / (1.0 + re_val) + g_val * self.m0 / (self.phi_B - self.phi_A)
        return CandidateScalars(Re=re_val, G=g_val, m0=self.m0, c=c)

    def scalar(self, monitors: Any, t: int, T: int) -> float:
        return self.evaluate(monitors, t, T).c

    def tensor(self, monitors: Any, t: int, T: int, dim: Optional[int] = None):
        c = self.scalar(monitors, t, T)
        if dim is None:
            return c
        return float(c) * np.eye(int(dim), dtype=np.float64)

    def describe(self) -> dict:
        return {
            "p": self.p,
            "tau": self.tau,
            "k": self.k,
            "g0": self.g0,
            "g_ramp": self.g_ramp,
            "phi_A": self.phi_A,
            "phi_B": self.phi_B,
            "L": self.L,
            "v": self.v,
            "m0": self.m0,
            "re_coefficient": self.re_coefficient,
            "canonical_bridge": False,
            "note": (
                "RES-606 §5 conformal candidate. Not the canonical "
                "RES-601 §7 bridge. No directional content."
            ),
        }


__all__ = [
    "LowRankMetricHead",
    "BridgeMetricHead",
    "CandidateBridgeMetricHead",
    "CandidateScalars",
]
