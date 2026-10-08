"""
Sigma-1 safety gate. Deterministic regime switch.
Owning doc: RES-303.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SigmaAction(str, Enum):
    CLEANUP = "CLEANUP"
    REEMBED = "REEMBED"
    REPULSE_ABSTAIN = "REPULSE_ABSTAIN"
    NONE = "NONE"


# Priority order is immutable (RES-303 §priority order)
PRIORITY = (SigmaAction.CLEANUP, SigmaAction.REEMBED, SigmaAction.REPULSE_ABSTAIN)


@dataclass
class SigmaGate:
    E_sigma: float
    k: int = 3

    def __post_init__(self) -> None:
        self._volume_fail_streak = 0
        self._prev_mu = 0

    def evaluate(self,
                 scar_energy: float,
                 mu: int,
                 volume_ok: bool,
                 requested: SigmaAction | None = None) -> SigmaAction:
        """
        Returns the selected action, or NONE if the gate does not fire.
        Exactly one action is selected by frozen priority order (RES-303).
        """
        if not volume_ok:
            self._volume_fail_streak += 1
        else:
            self._volume_fail_streak = 0

        triggers = (
            scar_energy > self.E_sigma,
            mu != self._prev_mu and scar_energy > self.E_sigma / 2.0,
            self._volume_fail_streak > self.k,
        )
        self._prev_mu = mu

        if not any(triggers):
            return SigmaAction.NONE

        if requested is not None and requested != SigmaAction.NONE:
            return requested
        return SigmaAction.CLEANUP  # top of PRIORITY
