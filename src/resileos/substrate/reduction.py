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
        psi_s         [1, T, rank] slow coordinate
        ode_error     scalar       MSE of the ODE fit
    """

    def __init__(self, hidden_dim: int,
                 L_H_kernel: torch.Tensor,
                 rank: int = 1):
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
        Q, _ = torch.linalg.qr(basis)
        self.register_buffer("basis", Q)                      # [D, rank]
        self.register_buffer("P_s", Q @ Q.transpose(0, 1))    # [D, D]

        self.f_scalar = nn.Parameter(torch.tensor(1.0))

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

        psi_s_full = trunk_state @ self.P_s          # [1, T, D]
        psi_s = psi_s_full @ self.basis              # [1, T, rank]
        psi_scalar = psi_s[..., 0:1]                 # [1, T, 1]

        pi_o = self.f_scalar * self.psi_a * self.psi_b
        pi_s = self.f_scalar * self.psi_b * (self.psi_b - self.psi_a)
        gamma_eff = G_field.mean() * (pi_o + pi_s)

        delta_psi = psi_scalar - self.psi_b          # [1, T, 1]

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
            "rmse" — root-mean-square residual. Matches O(ε) norm bound.
                     Expected slope ≈ 1.
            "mse"  — mean-square residual. Expected slope ≈ 2.

        Args:
            trajectory_factory: callable(eps) -> trunk_state [1, T, D]
            epsilons:           iterable of positive floats
            G_field:            [1, T, 1]
            metric:             "rmse" | "mse"

        Returns dict with metric, epsilons, errors, slope, intercept, r_squared.
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


# ── trajectory generators (shared by CLI and API) ────────────────────────
def simulate_linear_ode(
    hidden_dim: int,
    seq_len: int,
    gamma_true: float,
    psi_b: float = 1.5,
    noise: float = 0.0,
    seed: int = 0,
) -> torch.Tensor:
    """
    [1, T, D] trajectory whose first component follows δΨ̇ = −γ · δΨ
    exactly, embedded in a D-dimensional ambient space. Remaining
    components are small noise. Used by the test suite.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / max(seq_len - 1, 1)
    delta = np.zeros(seq_len, dtype=np.float64)
    delta[0] = 0.5
    for t in range(1, seq_len):
        delta[t] = delta[t - 1] - gamma_true * delta[t - 1] * dt
    psi = psi_b + delta

    trunk = rng.standard_normal((seq_len, hidden_dim)) * 0.05
    trunk[:, 0] = psi
    if noise > 0.0:
        trunk += rng.standard_normal(trunk.shape) * noise
    return torch.tensor(trunk[None, ...], dtype=torch.float32)


def simulate_axiom_d(
    dim: int,
    seq_len: int,
    epsilon: float,
    psi_a: float = 0.5,
    psi_b: float = 1.5,
    f: float = 1.0,
    g_field: float = 0.85,
    dt: float = 0.01,
    seed: int = 0,
    embed_noise: float = 0.02,
) -> torch.Tensor:
    """
    Integrate Axiom D on the slow coordinate and embed in dim-dimensional
    ambient space. Returns [1, T, D].

    Axiom D:
        dΨ/dt = −L_H Ψ + M_E · F(Ψ, f)
        F(Ψ, f) = f · Ψ(Ψ_A − Ψ)(Ψ − Ψ_B)

    with L_H = 0 on the slow subspace (by construction) and
    M_E = G · Ψ_B / (Ψ_B − Ψ_A) per Axiom C.

    The trajectory starts at Ψ = Ψ_B + ε and decays toward Ψ_B.
    """
    rng = np.random.default_rng(seed)
    m_e = g_field * psi_b / (psi_b - psi_a)

    psi = psi_b + epsilon
    traj = np.zeros(seq_len, dtype=np.float64)
    traj[0] = psi
    for t in range(1, seq_len):
        F_val = f * psi * (psi_a - psi) * (psi - psi_b)
        psi = psi + m_e * F_val * dt
        traj[t] = psi

    ambient = rng.standard_normal((seq_len, dim - 1)) * embed_noise
    full = np.concatenate([traj[:, None], ambient], axis=1)
    return torch.tensor(full[None, ...], dtype=torch.float32)
