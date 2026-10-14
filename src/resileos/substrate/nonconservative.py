"""
Non-conservative extension for the residual core.

A complex diagonal D = diag(d_1, ..., d_r) with prod(d_i) = 1 is applied
to the scar matrix. The effective step map becomes

    J = diag(D) + strict_lower(Lambda)

so det(J) = prod(d_i) = 1 is preserved, while the individual eigenvalues
of J are {d_1, ..., d_r} and can differ from 1.

Two modes:

    "conservative"       d_i = 1 for all i. J is unit lower triangular.
                         All eigenvalues are 1. Original core behavior.

    "non-conservative"   d_i = exp(g_i + i*theta_i) with sum(g) = 0 and
                         sum(theta) = 0, so prod(d_i) = exp(0) = 1.

The constraint sum(g) = 0 and sum(theta) = 0 is enforced after every
update.

Optional oscillator:

    If a KuramotoField is attached, the theta update is delegated to it
    when update() is called with an epsilon argument. This replaces the
    linear drive with real coupled-oscillator dynamics. If no oscillator
    is attached, or epsilon is not passed, the linear drive runs and
    behavior is unchanged.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

try:
    from .oscillator import KuramotoField, empty_coupling
except ImportError:
    KuramotoField = None  # type: ignore
    empty_coupling = None  # type: ignore


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
        Maximum |theta_i| in radians (linear drive only).
    decay : float
        First-order smoothing on g.
    oscillator : KuramotoField, optional
        If provided and mode is "non-conservative", the theta update
        uses real Kuramoto dynamics when update() is called with
        epsilon. Otherwise the linear drive runs.
    """

    def __init__(self, r: int, mode: str = "conservative",
                 gamma_max: float = 0.5,
                 phase_max: float = 0.4,
                 decay: float = 0.9,
                 oscillator: Optional["KuramotoField"] = None):
        if mode not in ("conservative", "non-conservative"):
            raise ValueError(f"mode: {mode!r}")
        self.r = r
        self.mode = mode
        self.gamma_max = float(gamma_max)
        self.phase_max = float(phase_max)
        self.decay = float(decay)

        self.g = np.zeros(r, dtype=np.float64)
        self.theta = np.zeros(r, dtype=np.float64)

        idx = np.arange(r, dtype=np.float64)
        self.g_pattern = np.sin(2.0 * np.pi * idx / max(r, 1))
        self.g_pattern -= self.g_pattern.mean()
        self.t_pattern = np.cos(2.0 * np.pi * idx / max(r, 1))
        self.t_pattern -= self.t_pattern.mean()

        self.oscillator = oscillator
        self.W: Optional[np.ndarray] = None
        self._oscillator_enabled = False

    # ── coupling attachment ─────────────────────────────────────────
    def attach_coupling(self, W: np.ndarray) -> None:
        """Set the (r, r) coupling matrix used by the oscillator."""
        W = np.asarray(W, dtype=np.float64)
        if W.shape != (self.r, self.r):
            raise ValueError(f"W shape {W.shape} != ({self.r}, {self.r})")
        self.W = W

    # ── drive ───────────────────────────────────────────────────────
    def update(self, F_res: float, DeltaS: float, mu: int,
               epsilon: Optional[float] = None) -> None:
        """
        Update g and theta from monitors.

        F_res    : residual flux magnitude
        DeltaS   : sharpness
        mu       : parity (0 or 1)
        epsilon  : tracking error. When provided AND an oscillator is
                   attached, the theta update is delegated to the
                   KuramotoField. Otherwise the linear drive runs.
        """
        if self.mode == "conservative":
            return

        # Magnitude drive (unchanged)
        drive_g = np.tanh(abs(F_res) + DeltaS) * self.gamma_max
        self.g = self.decay * self.g + (1.0 - self.decay) * drive_g * self.g_pattern
        self.g -= self.g.mean()

        # Phase drive: oscillator or linear
        if (self.oscillator is not None
                and epsilon is not None
                and self.mode == "non-conservative"):
            W = self.W if self.W is not None else empty_coupling(self.r)
            self.oscillator.theta = self.theta.copy()
            new_theta = self.oscillator.step(float(epsilon), W)
            self.theta = new_theta
            self._oscillator_enabled = True
        else:
            drive_t = (2.0 * mu - 1.0) * self.phase_max * self.t_pattern
            self.theta = self.theta + drive_t
            self.theta -= self.theta.mean()
            self._oscillator_enabled = False

    # ── outputs ─────────────────────────────────────────────────────
    def diagonal(self) -> np.ndarray:
        """Complex diagonal d_i = exp(g_i + i theta_i), prod(d_i) = 1."""
        return np.exp(self.g + 1j * self.theta)

    def effective_matrix(self, Lambda: np.ndarray) -> np.ndarray:
        D = self.diagonal()
        L = np.tril(np.asarray(Lambda, dtype=np.complex128), k=-1)
        return np.diag(D).astype(np.complex128) + L

    def anisotropy(self) -> float:
        mags = np.abs(self.diagonal())
        return float(mags.max() / (mags.min() + 1e-300))

    def order_parameter(self) -> float:
        z = np.exp(1j * self.theta)
        return float(np.abs(np.mean(z)))

    def reset(self) -> None:
        self.g[:] = 0.0
        self.theta[:] = 0.0
        if self.oscillator is not None:
            self.oscillator.reset()

    @property
    def using_oscillator(self) -> bool:
        return self._oscillator_enabled

    # ── persistence ─────────────────────────────────────────────────
    def state_dict(self) -> dict:
        d = {
            "g": self.g.tolist(),
            "theta": self.theta.tolist(),
            "mode": self.mode,
            "gamma_max": self.gamma_max,
            "phase_max": self.phase_max,
            "decay": self.decay,
        }
        if self.oscillator is not None:
            d["oscillator"] = self.oscillator.state_dict()
        if self.W is not None:
            d["W"] = self.W.tolist()
        return d

    def load_state_dict(self, d: dict) -> None:
        self.g = np.asarray(d["g"], dtype=np.float64)
        self.theta = np.asarray(d["theta"], dtype=np.float64)
        self.mode = d.get("mode", self.mode)
        self.gamma_max = float(d.get("gamma_max", self.gamma_max))
        self.phase_max = float(d.get("phase_max", self.phase_max))
        self.decay = float(d.get("decay", self.decay))
        if "oscillator" in d and self.oscillator is not None:
            self.oscillator.load_state_dict(d["oscillator"])
        if "W" in d:
            self.W = np.asarray(d["W"], dtype=np.float64)


__all__ = ["NonConservativeOperator"]
