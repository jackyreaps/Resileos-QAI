"""
Opt-in ternary quantizer for RES-401 front-end only.

Merge into training.py (or import from here during experiment):
  - ste_ternary alongside ste_sign
  - FrontEndEncoder(mode="bipolar"|"ternary", tau=...)
  - Default mode remains "bipolar" so existing tests stay green.

Frozen core is untouched.
"""
from __future__ import annotations

from typing import Literal

import numpy as np


def ste_sign(x: np.ndarray) -> np.ndarray:
    """Forward: sign. Backward: identity (straight-through)."""
    return np.where(x >= 0.0, 1.0, -1.0)


def ste_ternary(x: np.ndarray, tau: float = 0.05) -> np.ndarray:
    """
    Forward: {-1, 0, +1} with threshold tau on |x|.
    Backward (analytic STE used in loss_and_grads): treat as identity
    through the quantizer (same STE family as ste_sign).
    """
    y = np.zeros_like(x, dtype=np.float32)
    y[x > tau] = 1.0
    y[x < -tau] = -1.0
    return y


def ternary_to_bipolar(Ub: np.ndarray, Vb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compatibility map for frozen bipolar core: zeros -> +1."""
    return (
        np.where(Ub == 0.0, 1.0, Ub).astype(np.float32),
        np.where(Vb == 0.0, 1.0, Vb).astype(np.float32),
    )


class FrontEndEncoder:
    """
    Produces Ub, Vb, and residual-scale fields from a weight block W.
    Only P and Q are trainable. Per RES-401 §scope.

    mode="bipolar"  -> ste_sign  (default, production)
    mode="ternary"  -> ste_ternary (opt-in experiment)
    """

    def __init__(
        self,
        m: int,
        n: int,
        r: int,
        seed: int = 0,
        mode: Literal["bipolar", "ternary"] = "bipolar",
        tau: float = 0.05,
    ):
        rng = np.random.default_rng(seed)
        self.P = rng.standard_normal((n, r)) * 0.1
        self.Q = rng.standard_normal((r, m)) * 0.1
        self.m, self.n, self.r = m, n, r
        self.mode = mode
        self.tau = float(tau)

    def _quantize(self, pre: np.ndarray) -> np.ndarray:
        if self.mode == "ternary":
            return ste_ternary(pre, tau=self.tau)
        return ste_sign(pre).astype(np.float32)

    def forward(self, W: np.ndarray) -> dict[str, np.ndarray]:
        U_pre = W @ self.P
        V_pre = self.Q @ W
        return {
            "Ub": self._quantize(U_pre),
            "Vb": self._quantize(V_pre),
            "U_pre": U_pre,
            "V_pre": V_pre,
            "mode": self.mode,
        }

    def factors_for_core(self, enc_out: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """Factors safe to pass into frozen bipolar ResidualCore."""
        Ub, Vb = enc_out["Ub"], enc_out["Vb"]
        if self.mode == "ternary":
            return ternary_to_bipolar(Ub, Vb)
        return Ub.astype(np.float32), Vb.astype(np.float32)
