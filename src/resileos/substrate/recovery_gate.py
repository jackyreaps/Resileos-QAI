"""F2 recovery → abstention gate (framework product wire).

Uses KuramotoField recovery_loss / recovery_time as an *optional*
confidence veto alongside Titanos order-parameter abstention (RES-302).

Policy (additive, does not replace RES-302):
  - If recovery_loss(field, target) > loss_max  → recommend ABSTAIN
  - If recovery_time(...) is None within max_steps → recommend ABSTAIN
  - Else → CONTINUE (leave Titanos confidence gate in charge)

This is the thread ℛ stand-in (operational). Full chiral ℛ remains
on the private track.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .oscillator import KuramotoField
from .recovery import RecoveryTarget, recovery_loss, recovery_time


@dataclass
class RecoveryGateDecision:
    action: str  # "CONTINUE" | "ABSTAIN"
    recovery_loss: float
    recovery_steps: Optional[int]
    reason: str


def evaluate_recovery_gate(
    field: KuramotoField,
    *,
    target: Optional[RecoveryTarget] = None,
    W: Optional[np.ndarray] = None,
    loss_max: float = 0.15,
    perturb_probe: Optional[np.ndarray] = None,
    max_steps: int = 50,
    copy_field: bool = True,
) -> RecoveryGateDecision:
    """Evaluate whether the phase field is near its synchron target."""
    target = target or RecoveryTarget(kind="order", r_min=0.85)
    theta = field.theta
    loss = float(recovery_loss(theta, target))
    if loss > loss_max:
        return RecoveryGateDecision(
            action="ABSTAIN",
            recovery_loss=loss,
            recovery_steps=None,
            reason=f"recovery_loss {loss:.4f} > loss_max {loss_max}",
        )

    steps: Optional[int] = 0
    if perturb_probe is not None:
        f = KuramotoField(
            r=field.r,
            kappa=field.kappa,
            alpha=getattr(field, "alpha", 0.5),
            ladder=getattr(field, "ladder", "golden_powers"),
            seed=0,
        )
        f.omega = np.asarray(field.omega, dtype=np.float64).copy()
        f.theta = np.asarray(field.theta, dtype=np.float64).copy()
        steps = recovery_time(
            f, perturb_probe, target, max_steps=max_steps, W=W,
        )
        if steps is None:
            return RecoveryGateDecision(
                action="ABSTAIN",
                recovery_loss=loss,
                recovery_steps=None,
                reason=f"no recovery within {max_steps} steps after probe kick",
            )

    return RecoveryGateDecision(
        action="CONTINUE",
        recovery_loss=loss,
        recovery_steps=steps,
        reason="field within recovery target",
    )


__all__ = ["RecoveryGateDecision", "evaluate_recovery_gate"]
