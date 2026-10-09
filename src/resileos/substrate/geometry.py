"""
Head 1: geometric manifold tracking.

SPECIFICATION COMPLIANCE STATUS:
    LowRankMetricHead   — STRUCTURAL PROXY SUBSTITUTE (see RES-602 §3).
                          Uses g = L Lᵀ + εI, not the RES-601 §7 bridge.
                          Requires explicit labelling per RES-602 §5.4.
    BridgeMetricHead    — CANONICAL METRIC BRIDGE (RES-601 §7).
                          Locked until rheology coordinates x are derived.
                          Raises NotImplementedError.
"""
from __future__ import annotations

import torch
import torch.nn as nn


class LowRankMetricHead(nn.Module):
    """
    SPECIFICATION COMPLIANCE STATUS: STRUCTURAL PROXY SUBSTITUTE.

    Implements g = L Lᵀ + εI where L_t = trunk_state_t · W_L, projected
    per time step. This is NOT the canonical metric bridge of RES-601 §7.

    Provides covariant parallel transport penalty ||∇_X V||² via Woodbury
    inverse on the low-rank metric:
        g⁻¹ = (1/ε)(I − L(LᵀL + εI_r)⁻¹Lᵀ)

    Inputs:
        trunk_state  [1, T, D]     temporal trajectory tensors
        X_direction  [1, T, D]     directional velocity field
    Returns:
        V_seq        [1, T, D]     intentionality vectors
        loss         scalar        mean ||∇_X V||²
    """

    def __init__(self, hidden_dim: int, low_rank_dim: int = 32,
                 epsilon: float = 1e-3):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.low_rank_dim = low_rank_dim
        self.epsilon = epsilon

        # Parameter initialisation: scaled to unit variance per input dim.
        self.W_L = nn.Parameter(
            torch.randn(hidden_dim, low_rank_dim) / (hidden_dim ** 0.5)
        )
        self.W_V = nn.Parameter(
            torch.randn(hidden_dim, hidden_dim) / (hidden_dim ** 0.5)
        )

    def forward(self, trunk_state: torch.Tensor,
                X_direction: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # ── shape checks (RES-602 §5.4: batch=1 for coordinate parsing) ──
        if trunk_state.dim() != 3 or trunk_state.size(0) != 1:
            raise ValueError(
                f"trunk_state must be [1, T, D], got {tuple(trunk_state.shape)}"
            )
        if X_direction.shape != trunk_state.shape:
            raise ValueError(
                f"X_direction {tuple(X_direction.shape)} must match "
                f"trunk_state {tuple(trunk_state.shape)}"
            )

        B, T, D = trunk_state.shape
        if D != self.hidden_dim:
            raise ValueError(
                f"hidden_dim {self.hidden_dim} != trunk last dim {D}"
            )

        r = self.low_rank_dim
        eps = self.epsilon

        # ── per-step low-rank factors ────────────────────────────────────
        # L_seq[t] = trunk_state[t] @ W_L, shape [T, D, r]
        L_seq = torch.einsum("td,dr->tdr", trunk_state.squeeze(0), self.W_L)
        V_seq = trunk_state.squeeze(0) @ self.W_V      # [T, D]
        X_seq = X_direction.squeeze(0)                 # [T, D]

        eye_r = torch.eye(r, device=trunk_state.device, dtype=trunk_state.dtype)
        loss_sum = trunk_state.new_zeros(())

        for t in range(T):
            L = L_seq[t]          # [D, r]
            V = V_seq[t]          # [D]
            X = X_seq[t]          # [D]

            LtL = L.transpose(0, 1) @ L                    # [r, r]
            reg_inv = torch.inverse(LtL + eps * eye_r)     # [r, r]

            def g_inv(vec: torch.Tensor) -> torch.Tensor:
                Lt_vec = L.transpose(0, 1) @ vec            # [r]
                sub = reg_inv @ Lt_vec                      # [r]
                return (vec - L @ sub) / eps                # [D]

            partial_V_X = self.W_V @ X                     # [D]

            W_L_X = self.W_L.transpose(0, 1) @ X           # [r]
            W_L_V = self.W_L.transpose(0, 1) @ V           # [r]
            L_X = L.transpose(0, 1) @ X                    # [r]
            L_V = L.transpose(0, 1) @ V                    # [r]

            term_1 = (L @ W_L_V) * X + (L @ W_L_X) * V     # [D]
            term_2 = self.W_L @ (L_V * W_L_X)              # [D]

            christoffel_V_X = 0.5 * g_inv(term_1 + term_2)

            nabla_X_V = partial_V_X + christoffel_V_X      # [D]
            loss_sum = loss_sum + torch.sum(nabla_X_V ** 2)

        return V_seq.unsqueeze(0), loss_sum / T


class BridgeMetricHead(nn.Module):
    """
    SPECIFICATION COMPLIANCE STATUS: CANONICAL METRIC BRIDGE (RES-601 §7).

    Implements: g_ij(x) = δ_ij · 1/(1 + Re_ε(x)) + (G(x)/(Ψ_B − Ψ_A)) · M_E^(ij)

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
