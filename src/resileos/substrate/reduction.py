"""
Head 2: FEP reduction tracking.

SPECIFICATION COMPLIANCE STATUS: CANONICAL FEP SUBSPACE VERIFIER.

Implements numerical verification of the Reduction_fep.md linearized
theorem. Follows RES-600 §4 and RES-602 §5.4:
    - f is a free learnable scalar (RES-600 §7)
    - P_s is a fixed kernel projector onto ker(L_H), not learned
    - δΨ_s = Ψ_s − Ψ_B applied per RES-600 §4
    - P_s may be rank-k; see class docstring for ODE scope note
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

    Rank handling:
        P_s may be rank-k. The scalar ODE fit uses the first coordinate.

    G-field handling:
        The ODE fit uses per-step Γ_eff(t) = G(t) · (Π_o + Π_s). When
        G_field is constant this reduces to the scalar form.

    Inputs:
        trunk_state   [1, T, D]
        G_field       [1, T, 1]
    Returns:
        psi_s         [1, T, rank]
        ode_error     scalar
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
        self.register_buffer("basis", Q)
        self.register_buffer("P_s", Q @ Q.transpose(0, 1))

        self.f_scalar = nn.Parameter(torch.tensor(1.0))

        self.register_buffer("psi_a", torch.tensor(0.5))
        self.register_buffer("psi_b", torch.tensor(1.5))

    def forward(self, trunk_state: torch.Tensor,
                G_field: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if trunk_state.dim() != 3 or trunk_state.size(0) != 1:
            raise ValueError(
                f"trunk_state must be [1, T, D], got {tuple(trunk_state.shape)}"
            )
        _, T, D = trunk_state.shape
        if D != self.hidden_dim:
            raise ValueError(
                f"hidden_dim {self.hidden_dim} != trunk last dim {D}"
            )
        if G_field.dim() != 3 or G_field.size(0) != 1 or G_field.size(1) != T:
            raise ValueError(
                f"G_field must be [1, T, 1], got {tuple(G_field.shape)}"
            )

        psi_s_full = trunk_state @ self.P_s
        psi_s = psi_s_full @ self.basis
        psi_scalar = psi_s[..., 0:1]

        pi_o = self.f_scalar * self.psi_a * self.psi_b
        pi_s = self.f_scalar * self.psi_b * (self.psi_b - self.psi_a)
        pi_sum = pi_o + pi_s

        delta_psi = psi_scalar - self.psi_b

        if T > 1:
            # Per-step Γ_eff(t) = G(t) · Π_sum, shape [1, T-1, 1]
            gamma_t = G_field[:, :-1, :] * pi_sum
            d_dt = delta_psi[:, 1:, :] - delta_psi[:, :-1, :]
            expected = -gamma_t * delta_psi[:, :-1, :]
            ode_error = F.mse_loss(d_dt, expected)
        else:
            ode_error = trunk_state.new_zeros(())

        return psi_s, ode_error

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

        Returns dict with metric, epsilons, errors, slope, intercept,
        r_squared.
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


# ── trajectory generators ───────────────────────────────────────────────
def simulate_linear_ode(
    hidden_dim: int,
    seq_len: int,
    gamma_true: float,
    psi_b: float = 1.5,
    noise: float = 0.0,
    seed: int = 0,
) -> torch.Tensor:
    """[1, T, D] trajectory following δΨ̇ = −γ·δΨ. Used by tests."""
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
    # stress knobs
    off_manifold_frac: float = 0.0,
    g_ramp: float = 0.0,
    dt_coarse: float = 1.0,
    return_g_series: bool = False,
):
    """
    Integrate Axiom D on the slow coordinate and embed in dim-dimensional
    ambient space.

    Axiom D:
        dΨ/dt = −L_H Ψ + M_E(t) · F(Ψ, f)
        F(Ψ, f) = f · Ψ(Ψ_A − Ψ)(Ψ − Ψ_B)
        M_E(t) = G(t) · Ψ_B / (Ψ_B − Ψ_A)          per Axiom C

    Stress parameters (all default to ideal behavior):

        off_manifold_frac:
            Fraction of ε that leaks off the slow axis into the ambient
            subspace at t=0. The slow-axis starting value is reduced by
            the same fraction so total ε magnitude is preserved.
            Ideal = 0.0. Stress range 0.0 – 0.5.
            NOTE: with the current axis-aligned basis (e_0), this does
            not change psi_s; it is a placeholder for future multi-axis
            extensions.

        g_ramp:
            Fractional drift of G over the trajectory. G(t) goes from
            g_field to g_field·(1 + g_ramp). Modulates the decay RATE
            inside the integrator — the trajectory stays on-manifold,
            only Γ_eff(t) varies. Ideal = 0.0. Stress range 0.0 – 0.3.

        dt_coarse:
            Multiplier on the integration step. Ideal = 1.0.
            Stress range 1.0 – 8.0.

    Returns:
        trunk           [1, T, D] if return_g_series is False
        (trunk, G_series)  if return_g_series is True
                          G_series is [1, T, 1] as fed to the integrator.
    """
    rng = np.random.default_rng(seed)
    dt_eff = dt * dt_coarse

    # G(t): constant unless g_ramp > 0
    if g_ramp > 0.0:
        g_series = g_field * (1.0 + np.linspace(0.0, g_ramp, seq_len))
    else:
        g_series = np.full(seq_len, g_field, dtype=np.float64)

    # Slow-axis start: ε reduced by off-manifold leak
    psi = psi_b + epsilon * (1.0 - off_manifold_frac)
    traj = np.zeros(seq_len, dtype=np.float64)
    traj[0] = psi

    for t in range(1, seq_len):
        g_t = g_series[t]
        m_e_t = g_t * psi_b / (psi_b - psi_a)
        F_val = f * psi * (psi_a - psi) * (psi - psi_b)
        psi = psi + m_e_t * F_val * dt_eff
        traj[t] = psi

    ambient = rng.standard_normal((seq_len, dim - 1)) * embed_noise
    if off_manifold_frac > 0.0 and dim > 1:
        leak_dir = rng.standard_normal(dim - 1)
        leak_dir /= (np.linalg.norm(leak_dir) + 1e-12)
        leak = epsilon * off_manifold_frac * leak_dir[None, :]
        ambient = ambient + leak

    full = np.concatenate([traj[:, None], ambient], axis=1)
    trunk = torch.tensor(full[None, ...], dtype=torch.float32)

    if return_g_series:
        g_tensor = torch.tensor(g_series[None, :, None], dtype=torch.float32)
        return trunk, g_tensor
    return trunk
