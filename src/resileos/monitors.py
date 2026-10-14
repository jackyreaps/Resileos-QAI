"""
Monitor surface: the substrate's public read-only outputs.

ResidualCore.monitors() returns a MonitorBundle assembled from the
last packet and the non-conservative operator. No new computation; a
stable public accessor for outer loops and carrier features.

epsilon_from_monitors() composes a scalar tracking error from a
bundle. The form is a heuristic, not derived; it uses the same
monitors the substrate already emits.

No framework-specific names. Every field here exists in the packet
(RES-201) or on the operator (RES-200 §extension).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class MonitorBundle:
    """
    Snapshot of the substrate's monitor state after a step.

    Fields
    ------
    F_res           residual flux magnitude from the packet
    DeltaS          sharpness from the packet
    mu              parity, 0 or 1
    lambda_energy   Frobenius norm of the scar matrix
    anisotropy      max|d_i| / min|d_i| on the operator's diagonal
    volume          |det J|
    rank            Prime-Tower rank at this step
    schedule_index  step index at emission
    """
    F_res: float
    DeltaS: float
    mu: int
    lambda_energy: float
    anisotropy: float
    volume: float
    rank: int
    schedule_index: int

    def as_array(self) -> np.ndarray:
        return np.array([
            self.F_res, self.DeltaS, float(self.mu),
            self.lambda_energy, self.anisotropy,
            self.volume, float(self.rank), float(self.schedule_index),
        ], dtype=np.float64)

    def to_dict(self) -> dict:
        return {
            "F_res": float(self.F_res),
            "DeltaS": float(self.DeltaS),
            "mu": int(self.mu),
            "lambda_energy": float(self.lambda_energy),
            "anisotropy": float(self.anisotropy),
            "volume": float(self.volume),
            "rank": int(self.rank),
            "schedule_index": int(self.schedule_index),
        }


def epsilon_from_monitors(bundle: MonitorBundle,
                          alpha_floor: float = 1e-3) -> float:
    """
    Compose a tracking-error scalar from packet monitors.

    Form (heuristic):

        chaos = max(anisotropy - 1, 0)
        ε = |F_res| + 0.5 * |ΔS| + chaos

    Semantics match KuramotoField Option A: low ε → strong coupling,
    high ε → weak coupling. Large residual flux (uncertain
    reconstruction) and high anisotropy (basin asymmetry) push ε up,
    weakening coupling and broadening search.

    Bounded below by alpha_floor so gain kappa / (alpha + ε) stays
    finite when both F_res and DeltaS are near zero.
    """
    chaos = max(float(bundle.anisotropy) - 1.0, 0.0)
    eps = abs(float(bundle.F_res)) + 0.5 * abs(float(bundle.DeltaS)) + chaos
    return max(float(eps), float(alpha_floor))


def pack_extra_monitors(bundle: MonitorBundle,
                        csi: Optional[float] = None,
                        R: Optional[float] = None) -> np.ndarray:
    """
    Pack three or five scalars suitable for SubstrateCarrier.extra.

    Always includes lambda_energy, anisotropy, and a normalized rank.
    Optionally includes csi and R when the caller has them (they live
    above the core, in the sandbox and the oscillator field).

    Layout:
        [lambda_energy, anisotropy, rank/100]                     (3)
        + [csi]                                                    (4)
        + [R]                                                      (5)
    """
    parts = [
        float(bundle.lambda_energy),
        float(bundle.anisotropy),
        float(bundle.rank) / 100.0,
    ]
    if csi is not None:
        parts.append(float(csi))
    if R is not None:
        parts.append(float(R))
    return np.array(parts, dtype=np.float64)


__all__ = [
    "MonitorBundle",
    "epsilon_from_monitors",
    "pack_extra_monitors",
]
