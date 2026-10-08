"""
Abstention state machine and parity invariant.
Owning doc: RES-302.
"""
from __future__ import annotations

from dataclasses import dataclass

CONTINUE, REPULSE, CLEANUP, ABSTAIN = "CONTINUE", "REPULSE", "CLEANUP", "ABSTAIN"


@dataclass(frozen=True)
class AbstentionInputs:
    DeltaS: float
    mu: int
    scar_energy: float
    volume_ok: bool


@dataclass(frozen=True)
class AbstentionThresholds:
    E_sat: float
    tau_sat: float
    tau_low: float


def route_signals(inputs: AbstentionInputs,
                  th: AbstentionThresholds,
                  sigma1_action: str | None = None) -> str:
    """
    Frozen priority (RES-302 §3, RES-303 §precedence):
        sigma1 > volume_ok > abstention machine
    Returns one of {CONTINUE, REPULSE, CLEANUP, ABSTAIN}.
    """
    if sigma1_action is not None and sigma1_action != "NONE":
        return sigma1_action
    if not inputs.volume_ok:
        return ABSTAIN
    if inputs.scar_energy > th.E_sat or inputs.DeltaS > th.tau_sat:
        return CLEANUP
    if int(inputs.mu) == 1:
        return REPULSE
    if inputs.DeltaS < th.tau_low:
        return ABSTAIN
    return CONTINUE


# ── Parity invariant (RES-302 §parity invariant) ─────────────────────────
@dataclass
class ParityState:
    mu: int = 0
    theta_hi: float = 0.0
    theta_lo: float = 0.0

    def update(self, F_res: float) -> tuple[int, bool]:
        """
        Returns (mu, flipped). A flip without crossing is impossible by
        construction — flips only occur on threshold crossings (RES-302).
        """
        prev = self.mu
        if F_res > self.theta_hi:
            self.mu = 1
        elif F_res < -self.theta_lo:
            self.mu = 0
        return self.mu, (self.mu != prev)


def calibrate_parity(F_res_warm: list[float]) -> tuple[float, float]:
    """RES-302 §calibration: θ_hi = q0.95(F_res), θ_lo = -q0.05(F_res)."""
    import numpy as np
    arr = np.asarray(F_res_warm, dtype=np.float64)
    return float(np.quantile(arr, 0.95)), float(-np.quantile(arr, 0.05))
