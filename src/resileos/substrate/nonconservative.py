"""
Non-conservative extension for the residual core.

A complex diagonal D = diag(d_1, ..., d_r) with prod(d_i) = 1 is applied
to the scar matrix. The effective step map becomes

    J = diag(D) + strict_lower(Lambda)

so det(J) = prod(d_i) = 1 is preserved, while the individual eigenvalues
of J are {d_1, ..., d_r} and can differ from 1. The magnitudes of d_i
("non-conservative gamma") and their phases ("phase regulation") evolve
from the monitors F_res, DeltaS, mu.

Two modes:

    "conservative"       d_i = 1 for all i. J is unit lower triangular.
                         All eigenvalues are 1. This is the original
                         behavior of the core.

    "non-conservative"   d_i = exp(g_i + i*theta_i) with sum(g) = 0 and
                         sum(theta) = 0, so prod(d_i) = exp(0) = 1.

The constraint sum(g) = 0 is enforced after every update. The constraint
sum(theta) = 0 likewise. Both are renormalized numerically, so det(D) = 1
holds to floating-point precision regardless of drive magnitudes.

OscGraph.det_one_add_strictLower guarantees det(I + strict_lower) = 1
for any commutative ring, including complex weights. This module
generalizes that to diag(D) + strict_lower with det(D) = 1; the
determinant argument is unchanged because the strict-lower part is
still nilpotent in the triangular sense.
"""
from __future__ import annotations

import numpy as np


class NonConservativeOperator:
    """
    Non-conservative diagonal D with det(D) = 1, driven by monitors.

    Parameters
    ----------
    r : int
        Matrix size (scar rank).
    mode : str
        "conservative" or "non-conservative".
    gamma_max : float
        Maximum |g_i| deviation in log space.
    phase_max : float
        Maximum |theta_i| in radians.
    decay : float
        First-order smoothing on g. Larger = slower response.
    """

    def __init__(self, r: int, mode: str = "conservative",
                 gamma_max: float = 0.5,
                 phase_max: float = 0.4,
                 decay: float = 0.9):
        if mode not in ("conservative", "non-conservative"):
            raise ValueError(f"unknown mode {mode!r}")
        self.r = r
        self.mode = mode
        self.gamma_max = float(gamma_max)
        self.phase_max = float(phase_max)
        self.decay = float(decay)

        # Internal state, both zero-sum vectors.
        self.g = np.zeros(r, dtype=np.float64)
        self.theta = np.zeros(r, dtype=np.float64)

        # Fixed pattern vectors that break rotational symmetry. Both are
        # made zero-sum at construction so the drive respects the
        # det(D) = 1 constraint automatically.
        idx = np.arange(r, dtype=np.float64)
        self.g_pattern = np.sin(2.0 * np.pi * idx / max(r, 1))
        self.g_pattern -= self.g_pattern.mean()
        self.t_pattern = np.cos(2.0 * np.pi * idx / max(r, 1))
        self.t_pattern -= self.t_pattern.mean()

    # ── drive ─────────────────────────────────────────────────────────
    def update(self, F_res: float, DeltaS: float, mu: int) -> None:
        """
        Update g and theta from monitors.

        F_res  : residual flux magnitude
        DeltaS : sharpness
        mu     : parity (0 or 1)
        """
        if self.mode == "conservative":
            return

        # Magnitude drive: large |F_res| or DeltaS pushes the diagonal
        # away from identity, up to gamma_max. Bounded by tanh so the
        # excursion saturates gracefully.
        drive_g = np.tanh(abs(F_res) + DeltaS) * self.gamma_max
        self.g = self.decay * self.g + (1.0 - self.decay) * drive_g * self.g_pattern
        self.g -= self.g.mean()  # enforce sum(g) = 0

        # Phase drive: parity alternates the sign of the phase excursion.
        # The pattern is zero-sum, so sum(theta) = 0 is preserved.
        drive_t = (2.0 * mu - 1.0) * self.phase_max * self.t_pattern
        self.theta = self.theta + drive_t
        self.theta -= self.theta.mean()  # enforce sum(theta) = 0

    # ── outputs ───────────────────────────────────────────────────────
    def diagonal(self) -> np.ndarray:
        """Complex diagonal d_i = exp(g_i + i theta_i), prod(d_i) = 1."""
        return np.exp(self.g + 1j * self.theta)

    def effective_matrix(self, Lambda: np.ndarray) -> np.ndarray:
        """
        J = diag(D) + strict_lower(Lambda). Complex in general.

        det(J) = prod(d_i) = 1 exactly.
        """
        D = self.diagonal()
        L = np.tril(np.asarray(Lambda, dtype=np.complex128), k=-1)
        return np.diag(D).astype(np.complex128) + L

    def anisotropy(self) -> float:
        """max|d_i| / min|d_i|. Exactly 1 in conservative mode."""
        mags = np.abs(self.diagonal())
        return float(mags.max() / (mags.min() + 1e-300))

    def reset(self) -> None:
        self.g[:] = 0.0
        self.theta[:] = 0.0

    # ── persistence ───────────────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "g": self.g.tolist(),
            "theta": self.theta.tolist(),
            "mode": self.mode,
            "gamma_max": self.gamma_max,
            "phase_max": self.phase_max,
            "decay": self.decay,
        }

    def load_state_dict(self, d: dict) -> None:
        self.g = np.asarray(d["g"], dtype=np.float64)
        self.theta = np.asarray(d["theta"], dtype=np.float64)
        self.mode = d.get("mode", self.mode)
        self.gamma_max = float(d.get("gamma_max", self.gamma_max))
        self.phase_max = float(d.get("phase_max", self.phase_max))
        self.decay = float(d.get("decay", self.decay))


__all__ = ["NonConservativeOperator"]
