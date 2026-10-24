"""Recovery product (F2) — ℛ / synchron as a measured quantity.

This is not the toy e_0 bias from the single-engine efficiency ablation.
It measures whether a Kuramoto phase field returns to a synchron target
after a perturbation, in finite steps.

Assumptions (explicit — thread ℛ may refine these later):

  A1. Target kinds
      - "order": recover high global order R = |mean exp(i θ)|
        (synchron lock, R → 1). Default product metric.
      - "phase": recover toward a stored reference phase vector θ*
        (circular mean distance). Used when a specific configuration
        matters, not only coherence.

  A2. "Recovered" means both (when target is phase+order hybrid checks
      are optional):
      - order target: R >= r_min
      - phase target: mean circular distance to θ* <= eps

  A3. Dynamics: existing KuramotoField.step (RK4). No new integrator.

  A4. Private/thread ℛ (chiral / continuum-from-finite) is NOT encoded
      here. This module is the operational stand-in until that operator
      is ported. Marked in RecoveryTarget.kind and module docstring.

Off states:
  trainable          off
  GPU                off
  packet coupling    off (field-only; EngineGroup can wrap later)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .oscillator import KuramotoField


@dataclass(frozen=True)
class RecoveryTarget:
    """Synchron / phase target the field is expected to return to.

    kind:
      "order" — lock on order parameter R (default product claim)
      "phase" — lock on a reference phase vector
    """

    kind: str = "order"
    r_min: float = 0.85
    phase_ref: Optional[np.ndarray] = None
    eps_phase: float = 0.35  # rad, mean circular distance

    def __post_init__(self) -> None:
        if self.kind not in ("order", "phase"):
            raise ValueError(f"unknown RecoveryTarget.kind: {self.kind!r}")
        if self.kind == "phase" and self.phase_ref is None:
            raise ValueError("phase target requires phase_ref")
        if self.r_min < 0.0 or self.r_min > 1.0:
            raise ValueError("r_min must be in [0, 1]")


def circular_distance(theta: np.ndarray, ref: np.ndarray) -> float:
    """Mean absolute wrapped phase distance (radians)."""
    d = np.asarray(theta, dtype=np.float64) - np.asarray(ref, dtype=np.float64)
    d = ((d + np.pi) % (2.0 * np.pi)) - np.pi
    return float(np.mean(np.abs(d)))


def recovery_loss(field_state: np.ndarray, target: RecoveryTarget) -> float:
    """Scalar loss: 0 = fully recovered under the chosen target.

    order:  loss = max(0, r_min - R)
    phase:  loss = max(0, mean_circ_dist - eps_phase)
    """
    theta = np.asarray(field_state, dtype=np.float64)
    if target.kind == "order":
        z = np.exp(1j * theta)
        R = float(np.abs(np.mean(z)))
        return max(0.0, float(target.r_min) - R)
    assert target.phase_ref is not None
    dist = circular_distance(theta, target.phase_ref)
    return max(0.0, dist - float(target.eps_phase))


def recovery_time(
    field: KuramotoField,
    perturbation: np.ndarray,
    target: RecoveryTarget,
    *,
    tolerance: float = 1e-3,
    max_steps: int = 500,
    epsilon: float = 0.0,
    W: Optional[np.ndarray] = None,
) -> Optional[int]:
    """Steps until recovery_loss <= tolerance; None if not recovered.

    Applies perturbation additively to field.theta (wrapped), then steps
    the Kuramoto dynamics. This is the product metric: recovery as a
    measured step count, not only a loss value.
    """
    pert = np.asarray(perturbation, dtype=np.float64)
    if pert.shape != field.theta.shape:
        raise ValueError(
            f"perturbation shape {pert.shape} != theta {field.theta.shape}"
        )
    field.theta = ((field.theta + pert + np.pi) % (2.0 * np.pi)) - np.pi

    if recovery_loss(field.theta, target) <= tolerance:
        return 0

    for t in range(1, max_steps + 1):
        field.step(epsilon=epsilon, W=W)
        if recovery_loss(field.theta, target) <= tolerance:
            return t
    return None


def measure_recovery_product(
    *,
    r: int = 8,
    kappa: float = 2.0,
    n_trials: int = 20,
    perturb_scale: float = 0.8,
    max_steps: int = 400,
    seed: int = 0,
    r_min: float = 0.85,
) -> dict:
    """Monte Carlo recovery times under order-target (default product).

    Protocol:
      1. Build KuramotoField with coupling kappa * ones, golden ladder.
      2. Relax unperturbed until R >= r_min (or max_steps).
      3. Snapshot θ* as optional phase_ref for secondary stats.
      4. For each trial: copy field, apply random phase kick, measure
         recovery_time under order target.
    """
    rng = np.random.default_rng(seed)
    W = (kappa / max(r - 1, 1)) * (np.ones((r, r)) - np.eye(r))
    field = KuramotoField(r=r, kappa=1.0, alpha=0.5, ladder="golden_powers", seed=seed)
    # Identical natural frequencies so global lock is attainable.
    # Golden ladder is incommensurate by design and only partially
    # synchronizes; the product metric still uses order-parameter R.
    field.omega = np.full(r, field.omega_base / 4.0, dtype=np.float64)
    field.theta = rng.uniform(-np.pi, np.pi, size=r)
    # Burn-in toward synchron
    for _ in range(max_steps):
        field.step(epsilon=0.0, W=W)
        if field.order_parameter() >= r_min:
            break
    theta_lock = field.theta.copy()
    R_lock = float(field.order_parameter())

    target = RecoveryTarget(kind="order", r_min=r_min)
    times: list[Optional[int]] = []
    for i in range(n_trials):
        f = KuramotoField(r=r, kappa=1.0, alpha=0.5, ladder="golden_powers", seed=seed)
        f.omega = np.full(r, field.omega_base / 4.0, dtype=np.float64)
        f.theta = theta_lock.copy()
        pert = rng.normal(0.0, perturb_scale, size=r)
        steps = recovery_time(
            f, pert, target, tolerance=1e-3, max_steps=max_steps, W=W,
        )
        times.append(steps)

    recovered = [t for t in times if t is not None]
    return {
        "product": "recovery_F2",
        "assumptions": [
            "A1: default target is order-parameter lock (R>=r_min)",
            "A2: recovered iff recovery_loss <= 1e-3",
            "A3: KuramotoField RK4 dynamics",
            "A4: thread chiral ℛ not encoded; operational stand-in",
        ],
        "r": r,
        "kappa": kappa,
        "r_min": r_min,
        "n_trials": n_trials,
        "perturb_scale": perturb_scale,
        "R_after_burnin": R_lock,
        "n_recovered": len(recovered),
        "recovery_rate": len(recovered) / max(n_trials, 1),
        "median_steps": float(np.median(recovered)) if recovered else None,
        "mean_steps": float(np.mean(recovered)) if recovered else None,
        "max_steps_cap": max_steps,
        "times": times,
    }


__all__ = [
    "RecoveryTarget",
    "circular_distance",
    "recovery_loss",
    "recovery_time",
    "measure_recovery_product",
]
