"""
Causal Sandbox Index (CSI).

A scalar in (0, 1] measuring how closed a residual trajectory is:

    - volume residual     v_t = |log10(|det J_t|)|
    - internal prediction e_t^int = normalized step-to-step monitor change
    - external mismatch   e_t^ext = ||output - reference||, optional

Without living_factor:

    CSI_T = exp(-mean v) · exp(-mean e_int) · 1/(1 + mean e_ext)

With living_factor=True, the exp(-mean e_int) term is replaced (not
multiplied) by a bump around optimal_drift, so a completely frozen
trajectory does not automatically score highest:

    internal_term = exp(-k · (mean e_int − d*)^2)

At mean e_int = d* the internal term is 1. At mean e_int = 0 it is
exp(-k · d*²), a penalty for being frozen.

The claim, in this project's terms: finite residual trajectories that
maintain high CSI form more reliable causal subsystems, in the sense
that measurements internal to them are more trustworthy. This is a
working hypothesis, not a theorem. See RES-305 §0.

The general notion of finite dynamical systems forming closed causal
subsystems — where the meaningful measurements are internal to the
dynamics — has been discussed in relational-geometry contexts.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Sequence

import numpy as np


# ── component metrics ───────────────────────────────────────────────────
def volume_residual(det_J: float) -> float:
    """
    v_t = |log10(|det J_t|)|.

    Zero for a perfectly volume-preserving transform. Grows linearly in
    log-volume drift.
    """
    d = abs(float(det_J))
    if d <= 0.0:
        return math.inf
    return abs(math.log10(d + 1e-300))


def internal_prediction_error(
    current: Sequence[float],
    previous: Sequence[float],
    scale: Sequence[float] | None = None,
) -> float:
    """
    e_t^int: residual after a trivial "no change" prediction.

        e = || (current - previous) / scale ||_2

    When `scale` is None, uses max(|current|, |previous|, 1e-6)
    componentwise, so components with different natural magnitudes
    contribute comparably.
    """
    c = np.asarray(current, dtype=np.float64)
    p = np.asarray(previous, dtype=np.float64)
    if c.shape != p.shape:
        raise ValueError(f"shape mismatch: {c.shape} vs {p.shape}")
    diff = c - p
    if scale is None:
        denom = np.maximum(np.maximum(np.abs(c), np.abs(p)), 1e-6)
    else:
        denom = np.maximum(np.asarray(scale, dtype=np.float64), 1e-6)
    return float(np.linalg.norm(diff / denom))


# ── trajectory CSI ──────────────────────────────────────────────────────
def compute_csi(
    volume_residuals: Sequence[float],
    internal_errors: Sequence[float],
    external_errors: Sequence[float] | None = None,
    *,
    external_term: bool = True,
    living_factor: bool = False,
    optimal_drift: float = 0.1,
    living_sharpness: float = 4.0,
) -> float:
    """
    CSI over a trajectory.

    Without living_factor:
        CSI = exp(-mean v) · exp(-mean e_int)
              · [1/(1+mean e_ext)] if external_term

    With living_factor=True, the internal-error term is replaced by a
    bump around optimal_drift:

        internal_term = exp(-k · (mean e_int − d*)^2)

    Returns 1.0 for an empty trajectory (no evidence against closure).
    """
    v = np.asarray(volume_residuals, dtype=np.float64)
    e_int = np.asarray(internal_errors, dtype=np.float64)
    if v.size == 0 or e_int.size == 0:
        return 1.0
    if not np.all(np.isfinite(v)) or not np.all(np.isfinite(e_int)):
        return 0.0

    v_mean = float(v.mean())
    e_int_mean = float(e_int.mean())

    csi = math.exp(-v_mean)

    if living_factor:
        csi *= math.exp(-living_sharpness * (e_int_mean - optimal_drift) ** 2)
    else:
        csi *= math.exp(-e_int_mean)

    if external_term and external_errors is not None:
        e_ext = np.asarray(external_errors, dtype=np.float64)
        if e_ext.size > 0 and np.all(np.isfinite(e_ext)):
            csi /= (1.0 + float(e_ext.mean()))

    return float(csi)


class CSIState:
    """
    Rolling CSI over a fixed-size window of observations.

    Usage:

        csi_state = CSIState(window=64)
        for each step:
            csi_state.update(v_t, e_int_t)          # or with e_ext_t
        current_csi = csi_state.value()

    Empty state returns 1.0 by convention (no evidence against closure).
    """

    def __init__(self, window: int = 64, external_term: bool = True,
                 living_factor: bool = False,
                 optimal_drift: float = 0.1,
                 living_sharpness: float = 4.0):
        if window < 1:
            raise ValueError("window must be ≥ 1")
        self.window = int(window)
        self.external_term = bool(external_term)
        self.living_factor = bool(living_factor)
        self.optimal_drift = float(optimal_drift)
        self.living_sharpness = float(living_sharpness)

        self._v: deque[float] = deque(maxlen=self.window)
        self._e_int: deque[float] = deque(maxlen=self.window)
        self._e_ext: deque[float] = deque(maxlen=self.window)

    def update(self, v: float, e_int: float, e_ext: float = 0.0) -> None:
        self._v.append(float(v))
        self._e_int.append(float(e_int))
        self._e_ext.append(float(e_ext))

    def value(self) -> float:
        if not self._v:
            return 1.0
        return compute_csi(
            list(self._v), list(self._e_int),
            external_errors=list(self._e_ext) if self.external_term else None,
            external_term=self.external_term,
            living_factor=self.living_factor,
            optimal_drift=self.optimal_drift,
            living_sharpness=self.living_sharpness,
        )

    def samples(self) -> int:
        return len(self._v)

    def clear(self) -> None:
        self._v.clear()
        self._e_int.clear()
        self._e_ext.clear()

    # ── persistence ─────────────────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "window": self.window,
            "external_term": self.external_term,
            "living_factor": self.living_factor,
            "optimal_drift": self.optimal_drift,
            "living_sharpness": self.living_sharpness,
            "v": list(self._v),
            "e_int": list(self._e_int),
            "e_ext": list(self._e_ext),
        }

    def load_state_dict(self, d: dict) -> None:
        self.clear()
        for x in d.get("v", []):
            self._v.append(float(x))
        for x in d.get("e_int", []):
            self._e_int.append(float(x))
        for x in d.get("e_ext", []):
            self._e_ext.append(float(x))


# ── dual-path confidence ────────────────────────────────────────────────
def fast_confidence(cleanup_conf: float, sigma_eff: float, csi: float) -> float:
    """
    Blend the residual cleanup confidence with current sandbox health
    into a single fast-path confidence in [0, 1].

        fast_conf = (1 - exp(-cleanup_conf / (3·sigma_eff))) · csi

    When sigma_eff ≤ 0 (no stored items), reduces to a step function:
    nonzero cleanup_conf maps to 1.0, then gated by CSI.
    """
    if sigma_eff <= 0.0:
        conf_norm = 1.0 if cleanup_conf > 0.0 else 0.0
    else:
        conf_norm = 1.0 - math.exp(-cleanup_conf / (3.0 * sigma_eff))
    return float(max(0.0, min(1.0, conf_norm * csi)))


__all__ = [
    "volume_residual",
    "internal_prediction_error",
    "compute_csi",
    "CSIState",
    "fast_confidence",
]
