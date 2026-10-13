"""
Constructive head: produces a drift direction from the core's own
dynamics, without training and without a target vector.

Two mechanisms:

    trend   dΛ/dt extrapolation. Requires the previous step's Lambda.
            Direction = Vb @ (Λ_t − Λ_{t−1}) @ Ub.

    phase   Phase-driven rotation. Requires theta. Direction =
            Re(Ub @ J @ Vb) − Ub @ Vb, J = diag(exp(i·θ)) + strict_lower(Λ).

Both mechanisms are constructive and deterministic. Neither is trained.

Both are quantum-shaped mathematics in the sense of RES-308 §0:
complex numbers, unit-modulus phases, unitary phase rotations. Both
run on classical CPUs. No quantum capability is claimed.

The head does not modify the packet. The packet schema (RES-201) is
unchanged.
"""
from __future__ import annotations

import numpy as np


class ConstructiveHead:
    """
    Constructive direction head.

    Parameters:
        dim     ambient dimension (length of x_enc)
        m, n    block shape. m * n must be <= dim. If m * n < dim, the
                direction is zero-padded. If m * n > dim this raises.
        mode    "trend" | "phase" | "both"
        scale   multiplier applied to the returned direction
    """

    def __init__(self, dim: int, m: int, n: int,
                 mode: str = "trend", scale: float = 1.0):
        if m * n > dim:
            raise ValueError(f"m*n ({m*n}) > dim ({dim})")
        if mode not in ("trend", "phase", "both"):
            raise ValueError(f"unknown mode {mode!r}")
        self.dim = int(dim)
        self.m = int(m)
        self.n = int(n)
        self.mn = self.m * self.n
        self.mode = mode
        self.scale = float(scale)

    # ── public API ──────────────────────────────────────────────────────
    def forward(self, x_enc, packet,
                lambda_prev=None, theta=None) -> np.ndarray:
        if self.mode == "trend":
            return self._trend(packet, lambda_prev)
        if self.mode == "phase":
            return self._phase(packet, theta)
        return (self._trend(packet, lambda_prev)
                + self._phase(packet, theta))

    # ── internals ───────────────────────────────────────────────────────
    def _get(self, packet, key):
        if isinstance(packet, dict):
            return packet[key]
        return getattr(packet, key)

    def _embed(self, W_block: np.ndarray) -> np.ndarray:
        flat = np.asarray(W_block, dtype=np.float64).reshape(-1)
        if flat.size == self.dim:
            return flat
        out = np.zeros(self.dim, dtype=np.float64)
        out[:min(flat.size, self.dim)] = flat[:self.dim]
        return out

    def _trend(self, packet, lambda_prev) -> np.ndarray:
        if lambda_prev is None:
            return np.zeros(self.dim, dtype=np.float64)
        Ub = np.asarray(self._get(packet, "Ub"), dtype=np.float64)
        Vb = np.asarray(self._get(packet, "Vb"), dtype=np.float64)
        Lam = np.asarray(self._get(packet, "Lambda"), dtype=np.float64)
        Lp = np.asarray(lambda_prev, dtype=np.float64)
        if Lp.shape != Lam.shape:
            raise ValueError(
                f"lambda_prev shape {Lp.shape} != Lambda shape {Lam.shape}")
        dL = Lam - Lp
        W_trend = Ub @ dL @ Vb
        return self.scale * self._embed(W_trend)

    def _phase(self, packet, theta) -> np.ndarray:
        if theta is None:
            return np.zeros(self.dim, dtype=np.float64)
        Ub = np.asarray(self._get(packet, "Ub"), dtype=np.float64)
        Vb = np.asarray(self._get(packet, "Vb"), dtype=np.float64)
        Lam = np.asarray(self._get(packet, "Lambda"), dtype=np.complex128)
        theta = np.asarray(theta, dtype=np.float64).ravel()
        if theta.size != Lam.shape[0]:
            raise ValueError(
                f"theta length {theta.size} != rank {Lam.shape[0]}")
        D = np.exp(1j * theta)
        J = np.diag(D) + np.tril(Lam, k=-1)
        W_phase = np.real(Ub.astype(np.complex128)
                          @ J @ Vb.astype(np.complex128))
        W_base = Ub @ Vb
        return self.scale * self._embed(W_phase - W_base)

    def describe(self) -> dict:
        return {
            "dim": self.dim,
            "m": self.m,
            "n": self.n,
            "mn": self.mn,
            "mode": self.mode,
            "scale": self.scale,
            "trained": False,
            "quantum_capability": False,
            "quantum_shaped_math": True,
        }


__all__ = ["ConstructiveHead"]
