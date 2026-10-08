"""
HDRIFT adapter. Consumes the frozen control packet read-only.
Owning doc: RES-300. Acceptance band owned by RES-301.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from .moments import Seeds, build_moments


def holographic_drift(x_enc: np.ndarray,
                      mu_hv: np.ndarray,
                      nu_hv: np.ndarray,
                      scar_energy: float,
                      mu_parity: int,
                      repulsion: float = 0.1) -> tuple[np.ndarray, float]:
    """
    V(x) = <x, ν_hv> / <x, μ_hv> - x
    Step shrinks by scar energy; extra repulsion on μ = 1.
    Returns (drift, ratio). RES-300 §drift field.
    """
    denom = float(np.dot(x_enc, mu_hv))
    if abs(denom) < 1e-8:
        denom = 1e-8 if denom >= 0.0 else -1e-8
    ratio = float(np.dot(x_enc, nu_hv)) / denom
    attr = ratio - x_enc
    step = attr * (1.0 / (1.0 + scar_energy))
    if int(mu_parity) == 1:
        step = step - repulsion * x_enc
    return step, ratio


class HDRIFTAdapter:
    """
    Thin bridge. Never writes back to the classical core (RES-300 §contract).
    """

    def __init__(self,
                 dim: int,
                 seeds: Seeds,
                 drift_ratio_floor: float,
                 repulsion: float = 0.1,
                 target_cos: float = 0.3) -> None:
        self.dim = dim
        self.seeds = seeds
        self.drift_ratio_floor = drift_ratio_floor
        self.repulsion = repulsion
        self.target_cos = target_cos

    def step(self, packet: Any, x_enc: np.ndarray) -> dict[str, Any]:
        mu_hv, nu_hv = build_moments(packet, self.dim, self.seeds, self.target_cos)
        get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))
        scar_energy = float(np.linalg.norm(np.asarray(get("Lambda"))))
        drift_vec, ratio = holographic_drift(
            x_enc, mu_hv, nu_hv, scar_energy, int(get("mu")), self.repulsion
        )
        return {
            "drift": drift_vec,
            "ratio": ratio,
            "mu_hv": mu_hv,
            "nu_hv": nu_hv,
            "scar_energy": scar_energy,
        }

    def verify(self, packet: Any, x_enc_sample: Iterable[np.ndarray]) -> dict[str, Any]:
        """RES-301 acceptance: cos band + drift-ratio variance floor."""
        mu_hv, nu_hv = build_moments(packet, self.dim, self.seeds, self.target_cos)
        cos = float(np.dot(mu_hv, nu_hv)
                    / (np.linalg.norm(mu_hv) * np.linalg.norm(nu_hv) + 1e-12))
        cos_ok = 0.1 < cos < 0.5

        get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))
        scar_energy = float(np.linalg.norm(np.asarray(get("Lambda"))))
        mu_parity = int(get("mu"))

        ratios = [holographic_drift(x, mu_hv, nu_hv, scar_energy, mu_parity)[1]
                  for x in x_enc_sample]
        ratios = np.asarray(ratios, dtype=np.float64)
        var = float(np.var(ratios))
        mean = float(np.mean(ratios))
        std = float(np.std(ratios))
        snr = float("inf") if std < 1e-12 else abs(mean) / std
        var_ok = var > self.drift_ratio_floor

        return {
            "cos": cos, "cos_ok": cos_ok,
            "drift_ratio_mean": mean,
            "drift_ratio_std": std,
            "drift_ratio_variance": var,
            "drift_ratio_variance_ok": var_ok,
            "drift_ratio_snr": snr,
            "pass": cos_ok and var_ok,
        }
