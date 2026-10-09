"""
Head 2: FEP reduction tracking.

SPECIFICATION COMPLIANCE STATUS: CANONICAL FEP SUBSPACE VERIFIER.

Implements numerical verification of the Reduction_fep.md linearized
theorem. Follows RES-600 §4 and RES-602 §5.4:
    - f is a free learnable scalar (RES-600 §7)
    - P_s is a fixed kernel projector onto ker(L_H), not learned
    - δΨ_s = Ψ_s − Ψ_B applied per RES-600 §4
    - rank-1 P_s (simplification; rank-k is a future extension)
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class VerifiableFEPReductionHead(nn.Module):
    """
    Tracks the slow coordinate Ψ_s = P_s Ψ, evaluates the linearized ODE
    residual δΨ̇_s = −Γ_eff · δΨ_s, and provides an ε-sweep harness for
    verifying the C_1/λ_2 residual scaling claimed in RES-600 §4.

    Inputs:
        trunk_state   [1, T, D]    temporal trajectory
        G_field       [1, T, 1]    coherence field sequence
    Returns:
        psi_s         [1, T, 1]    slow coordinate
        ode_error     scalar       MSE of the ODE fit
    """

    def __init__(self, hidden_dim: int,
                 L_H_kernel: torch.Tensor,
                 rank: int = 1):
        """
        Args:
            hidden_dim:  state dimensionality
            L_H_kernel:  [hidden_dim, kernel_dim] orthonormal basis of ker(L_H)
            rank:        number of slow coordinates to track (default 1)
        """
        super().__init__()
        self.hidden_dim = hidden_dim
        self.rank = rank

        if L_H_kernel.shape[0] != hidden_dim:
            raise ValueError(
                f"L_H_kernel rows ({L_H_kernel.shape[0]}) must equal "
                f"hidden_dim ({hidden_dim})"
            )
        if L_H_kernel.shape[1] < rank:
            raise ValueError(
                f"kernel basis provides {L_H_kernel.shape[1]} columns, "
                f"rank={rank} requested"
            )

        basis = L_H_kernel[:, :rank]
        # Enforce orthonormality of the retained columns
        Q, _ = torch.linalg.qr(basis)
        self.register_buffer("basis", Q)                      # [D, rank]
        # P_s = Q Qᵀ  (orthogonal projector onto ker(L_H), rank-rank)
        self.register_buffer("P_s", Q @ Q.transpose(0, 1))    # [D, D]

        # Free scalar f (RES-600 §7: free parameter, not Re_ε·c)
        self.f_scalar = nn.Parameter(torch.tensor(1.0))

        # Well positions (fixed, not trained — they are properties of U(Ψ))
        self.register_buffer("psi_a", torch.tensor(0.5))
        self.register_buffer("psi_b", torch.tensor(1.5))

    # ── core forward ────────────────────────────────────────────────────
    def forward(self, trunk_state: torch.Tensor,
                G_field: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if trunk_state.dim() != 3 or trunk_state.size(0) != 1:
            raise ValueError(
                f"trunk_state must be [1, T, D], got {tuple(trunk_state.shape)}"
            )
        _, T, D = trunk_state.shape
        if D != self.hidden_dim:
            raise ValueError(f"hidden_dim {self.hidden_dim} != trunk last dim {D}")
        if G_field.dim() != 3 or G_field.size(0) != 1 or G_field.size(1) != T:
            raise ValueError(
                f"G_field must be [1, T, 1], got {tuple(G_field.shape)}"
            )

        # Ψ_s = P_s Ψ  →  [1, T, D]  (all mass on the rank-r subspace)
        psi_s_full = trunk_state @ self.P_s

        # Reduce to rank-r coordinates by projecting onto the basis
        # (basis is orthonormal, so this is a scalar/vector per step)
        psi_s = psi_s_full @ self.basis                    # [1, T, rank]

        # Scalar-well coupling: use only the first component if rank > 1
        psi_scalar = psi_s[..., 0:1]                        # [1, T, 1]

        # Precision terms from free f
        pi_o = self.f_scalar * self.psi_a * self.psi_b
        pi_s = self.f_scalar * self.psi_b * (self.psi_b - self.psi_a)
        gamma_eff = G_field.mean() * (pi_o + pi_s)          # scalar

        # Coordinate shift per RES-600 §4
        delta_psi = psi_scalar - self.psi_b                 # [1, T, 1]

        if T > 1:
            d_dt = delta_psi[:, 1:, :] - delta_psi[:, :-1, :]
            expected = -gamma_eff * delta_psi[:, :-1, :]
            ode_error = F.mse_loss(d_dt, expected)
        else:
            ode_error = trunk_state.new_zeros(())

        return psi_s, ode_error

    # ── verification harness ────────────────────────────────────────────
def sweep_epsilon(
        self,
        trajectory_factory,
        epsilons: list[float] | tuple[float, ...],
        G_field: torch.Tensor,
        metric: str = "rmse",
    ) -> dict:
        """
        Runs the ODE fit across multiple perturbation scales ε and fits
        the log-log slope of residual vs ε.

        metric:
            "rmse" — root-mean-square residual (norm). Matches the O(ε)
                     residual bound in RES-600 §4. Expected slope ≈ 1.
            "mse"  — mean-square residual (norm squared). Expected slope ≈ 2.

        Defaults to "rmse" because RES-600 §4 bounds a norm, not a norm².

        Args:
            trajectory_factory: callable(eps) -> trunk_state [1, T, D]
            epsilons:           iterable of positive floats
            G_field:            [1, T, 1] coherence field (same for all runs)
            metric:             "rmse" | "mse"

        Returns:
            {
              "metric":   "rmse" | "mse",
              "epsilons": [...],
              "errors":   [...],
              "slope":    float,
              "intercept":float,
              "r_squared":float,
            }
        """
        if metric not in ("rmse", "mse"):
            raise ValueError(f"metric must be 'rmse' or 'mse', got {metric!r}")

        eps_arr = np.asarray(epsilons, dtype=np.float64)
        errs = []
        for eps in eps_arr:
            trunk = trajectory_factory(float(eps))
            with torch.no_grad():
                _, err = self.forward(trunk, G_field)
            mse = max(float(err.item()), 1e-30)
            errs.append(mse ** 0.5 if metric == "rmse" else mse)
        err_arr = np.asarray(errs, dtype=np.float64)

        log_eps = np.log(eps_arr)
        log_err = np.log(err_arr)

        if len(eps_arr) >= 2:
            slope, intercept = np.polyfit(log_eps, log_err, 1)
            pred = slope * log_eps + intercept
            ss_res = float(np.sum((log_err - pred) ** 2))
            ss_tot = float(np.sum((log_err - log_err.mean()) ** 2)) + 1e-30
            r_squared = 1.0 - ss_res / ss_tot
        else:
            slope = intercept = float("nan")
            r_squared = float("nan")

        return {
            "metric": metric,
            "epsilons": eps_arr.tolist(),
            "errors": err_arr.tolist(),
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_squared),
        }


# ── structured trajectory generator for tests ───────────────────────────
def simulate_linear_ode(
    hidden_dim: int,
    seq_len: int,
    gamma_true: float,
    psi_b: float = 1.5,
    noise: float = 0.0,
    seed: int = 0,
) -> torch.Tensor:
    """
    Generates a [1, T, D] trajectory whose first component follows
    δΨ̇ = −gamma_true · δΨ exactly, embedded in a D-dim ambient space.

    Used to verify the reduction head recovers gamma_true when fed a
    trajectory that obeys the theorem. Remaining components are noise.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / max(seq_len - 1, 1)
    delta = np.zeros(seq_len, dtype=np.float64)
    delta[0] = 0.5                       # initial perturbation
    for t in range(1, seq_len):
        delta[t] = delta[t - 1] - gamma_true * delta[t - 1] * dt
    psi = psi_b + delta

    trunk = rng.standard_normal((seq_len, hidden_dim)) * 0.05
    trunk[:, 0] = psi
    if noise > 0.0:
        trunk += rng.standard_normal(trunk.shape) * noise
    return torch.tensor(trunk[None, ...], dtype=torch.float32)
