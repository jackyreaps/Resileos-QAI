"""
Directional diagnostic for HDRIFT (RES-308 / RES-300).

The stock holographic_drift is radial:

    V(x) = ratio - x,   ratio = <x, nu_hv> / <x, mu_hv>

That moves x along the line from the origin through x itself. The
hybrid reconstruction target is normalize(embed(Ub @ Vb)), a specific
unit vector that is not, in general, on that line. A radial update
cannot reduce the distance to a non-radial target.

This module does not claim predictive accuracy. It runs four modes so
the numbers stay honest:

    reconstruction  x <- normalize(embed(Ub @ Vb))
                    The drift IS the target. NRMSE = 0 by arithmetic.
                    Reports core reconstruction fidelity, not prediction.

    trend           single-step Lambda difference, projected to the
                    tangent plane at x. The only non-tautological
                    directional signal from the packet.

    multi_trend     average of the last K Lambda differences. Smooths
                    the trend direction across a rolling window.

    hybrid          reconstruction pull + w * trend. At w = 0 equals
                    reconstruction. At w > 0 the trend dilutes the pull.

All four modes are read-only. They do not write into the classical
core. The packet is unchanged (RES-201 frozen).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .adapter import HDRIFTAdapter
from .moments import Seeds
from .substrate.constructive import ConstructiveHead


def embed_block(W: np.ndarray, dim: int) -> np.ndarray:
    """Flatten a (m, n) block to length dim, zero-padded."""
    flat = np.asarray(W, dtype=np.float64).ravel()
    out = np.zeros(dim, dtype=np.float64)
    out[: min(flat.size, dim)] = flat[:dim]
    return out


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


def _tangent(d: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Remove the radial component of d with respect to x."""
    return d - float(np.dot(d, x)) * x


class DirectionalHDRIFT:
    """
    Read-only directional diagnostic.

    Modes:
        reconstruction  Tautology check.
        trend           Single-step Lambda-difference direction.
        multi_trend     Rolling average over the last `trend_window`
                        Lambda differences.
        hybrid          reconstruction + w * trend.

    Parameters
    ----------
    dim : int
        Ambient dimension.
    m, n : int
        Block shape. m * n must be <= dim.
    r : int
        Scar rank.
    mode : str
        One of the four modes.
    hybrid_trend_weight : float
        Only used in hybrid mode. 0.0 = pure reconstruction.
    trend_window : int
        Only used in multi_trend mode. Rolling average over the last
        `trend_window` Lambda differences. Default 4.
    seeds : Seeds, optional
        Seeds for the internal HDRIFTAdapter.
    seed : int
        Seed for the ConstructiveHead and the default Seeds.
    """

    def __init__(
        self,
        dim: int,
        m: int,
        n: int,
        r: int = 8,
        mode: str = "hybrid",
        hybrid_trend_weight: float = 0.0,
        trend_window: int = 4,
        seeds: Optional[Seeds] = None,
        seed: int = 0,
    ) -> None:
        if mode not in ("reconstruction", "trend", "multi_trend", "hybrid"):
            raise ValueError(mode)
        if not (0.0 <= hybrid_trend_weight <= 1.0):
            raise ValueError("hybrid_trend_weight must be in [0, 1]")
        if trend_window < 1:
            raise ValueError("trend_window must be >= 1")

        self.dim = int(dim)
        self.m, self.n, self.r = int(m), int(n), int(r)
        self.mode = mode
        self.hybrid_trend_weight = float(hybrid_trend_weight)
        self.trend_window = int(trend_window)
        self.seeds = seeds or Seeds.derived(seed)

        self.head = ConstructiveHead(dim, m, n, mode="trend", scale=1.0)
        self.adapter = HDRIFTAdapter(dim, self.seeds, drift_ratio_floor=1e-6)
        self._lambda_history: list[np.ndarray] = []

    def reset(self) -> None:
        self._lambda_history.clear()

    # ── packet access ────────────────────────────────────────────────
    def _get(self, packet: Any, key: str):
        return packet[key] if isinstance(packet, dict) else getattr(packet, key)

    def reconstruction_target(self, packet: Any) -> np.ndarray:
        Ub = np.asarray(self._get(packet, "Ub"), dtype=np.float64)
        Vb = np.asarray(self._get(packet, "Vb"), dtype=np.float64)
        return _unit(embed_block(Ub @ Vb, self.dim))

    # ── trend directions ─────────────────────────────────────────────
    def _single_step_trend(self, packet: Any) -> np.ndarray:
        if not self._lambda_history:
            return np.zeros(self.dim, dtype=np.float64)
        Lam = np.asarray(self._get(packet, "Lambda"), dtype=np.float64)
        Lam_prev = self._lambda_history[-1]
        if Lam_prev.shape != Lam.shape:
            return np.zeros(self.dim, dtype=np.float64)
        Ub = np.asarray(self._get(packet, "Ub"), dtype=np.float64)
        Vb = np.asarray(self._get(packet, "Vb"), dtype=np.float64)
        dL = Lam - Lam_prev
        return embed_block(Vb @ dL @ Ub, self.dim)

    def _multi_step_trend(self, packet: Any) -> np.ndarray:
        """
        (Lambda_t - Lambda_{t-window}) / window, lifted.
        Telescopes the individual step differences.
        """
        if len(self._lambda_history) < 2:
            return np.zeros(self.dim, dtype=np.float64)
        Lam = np.asarray(self._get(packet, "Lambda"), dtype=np.float64)
        Ub = np.asarray(self._get(packet, "Ub"), dtype=np.float64)
        Vb = np.asarray(self._get(packet, "Vb"), dtype=np.float64)
        window = min(self.trend_window, len(self._lambda_history))
        Lam_old = self._lambda_history[-window]
        if Lam_old.shape != Lam.shape:
            return np.zeros(self.dim, dtype=np.float64)
        dL = (Lam - Lam_old) / float(window)
        return embed_block(Vb @ dL @ Ub, self.dim)

    def trend_direction(self, x: np.ndarray, packet: Any,
                        mode: str = "trend") -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        if mode == "trend":
            d = self._single_step_trend(packet)
        elif mode == "multi_trend":
            d = self._multi_step_trend(packet)
        else:
            raise ValueError(mode)
        d = _tangent(d, x)
        return _unit(d)

    # ── step ─────────────────────────────────────────────────────────
    def step(self, x: np.ndarray, packet: Any) -> dict[str, Any]:
        x = np.asarray(x, dtype=np.float64)
        target = self.reconstruction_target(packet)
        holo = self.adapter.step(packet, x)
        scar = float(holo["scar_energy"])
        alpha = 1.0 / (1.0 + scar)
        w = self.hybrid_trend_weight

        if self.mode == "reconstruction":
            y = target.copy()
        elif self.mode in ("trend", "multi_trend"):
            d = self.trend_direction(x, packet, mode=self.mode)
            if np.linalg.norm(d) > 1e-12:
                step = float(np.dot(target - x, d))
                y = _unit(x + max(step, 0.0) * d)
            else:
                y = x.copy()
        elif self.mode == "hybrid":
            if w == 0.0:
                y = target.copy()
            else:
                pull = target - x
                d_c = self.trend_direction(x, packet, mode="trend")
                d = _tangent(pull + w * alpha * d_c, x)
                dn = float(np.linalg.norm(d))
                if dn > 1e-12:
                    d = d / dn
                    step = float(np.dot(target - x, d))
                    y = _unit(x + max(step, 0.0) * d)
                else:
                    y = x.copy()
        else:
            raise ValueError(self.mode)

        self._lambda_history.append(
            np.asarray(self._get(packet, "Lambda"), dtype=np.float64).copy()
        )
        max_hist = self.trend_window + 2
        if len(self._lambda_history) > max_hist:
            self._lambda_history = self._lambda_history[-max_hist:]

        label = (
            "reconstruction_tautology"
            if self.mode == "reconstruction" or
               (self.mode == "hybrid" and w == 0.0)
            else self.mode
        )

        return {
            "y": y,
            "target": target,
            "err_before": float(np.linalg.norm(x - target)),
            "err_after": float(np.linalg.norm(y - target)),
            "scar_energy": scar,
            "alpha": alpha,
            "mode": self.mode,
            "hybrid_trend_weight": w,
            "holo_ratio": float(holo["ratio"]),
            "label": label,
        }


def evaluate_modes(
    blocks: list[np.ndarray],
    r: int = 8,
    horizon: int = 4,
    trend_weights: tuple[float, ...] = (0.0, 0.25, 1.0),
    trend_window: int = 4,
) -> dict[str, Any]:
    """
    Report every mode on the same blocks.

    The "target" at each step is the reconstruction of the current
    packet. All modes are compared against a flat baseline: predict
    x_t for x_t (do nothing).
    """
    from .core import CoreConfig, ResidualCore

    dim = int(np.prod(blocks[0].shape))
    results: dict[str, Any] = {
        "label": (
            "Directional diagnostic. reconstruction is a tautology "
            "(drift IS the target). trend and multi_trend are "
            "non-tautological directional signals from the packet's scar "
            "dynamics. hybrid(w) mixes both; hybrid(w) < reconstruction "
            "means trend is net negative against the reconstruction target."
        ),
        "n_blocks": len(blocks),
        "horizon": horizon,
        "rank": r,
        "trend_window": trend_window,
    }

    def _run(mode: str, w: float = 0.0) -> dict[str, float]:
        reductions = []
        for i, W in enumerate(blocks):
            W = np.asarray(W, dtype=np.float64)
            m, n = W.shape
            core = ResidualCore(CoreConfig(m=m, n=n, r=r), seed=i)
            model = DirectionalHDRIFT(
                dim, m, n, r=r, mode=mode,
                hybrid_trend_weight=w,
                trend_window=trend_window,
                seed=i,
            )
            x = _unit(embed_block(W, dim))
            x_flat = x.copy()
            errs_m, errs_f = [], []
            for _ in range(horizon):
                packet = core.step(W)
                target = model.reconstruction_target(packet)
                out = model.step(x, packet)
                x = out["y"]
                errs_m.append(out["err_after"])
                errs_f.append(float(np.linalg.norm(x_flat - target)))
            base = float(np.sqrt(np.mean(np.square(errs_f))))
            mod = float(np.sqrt(np.mean(np.square(errs_m))))
            reductions.append(100.0 * (base - mod) / (base + 1e-12))
        return {
            "reduction_pct": float(np.mean(reductions)),
            "reduction_std": float(np.std(reductions)),
        }

    results["reconstruction"] = {
        **_run("reconstruction"),
        "note": "tautology: drift is the target",
    }
    results["trend"] = {
        **_run("trend"),
        "note": "single-step Lambda difference",
    }
    results["multi_trend"] = {
        **_run("multi_trend"),
        "note": f"rolling average of last {trend_window} Lambda differences",
    }
    results["hybrid"] = {}
    for w in trend_weights:
        results["hybrid"][f"weight_{w:g}"] = {
            **_run("hybrid", w),
            "note": (
                "equals reconstruction"
                if w == 0.0
                else "reconstruction diluted by trend"
            ),
        }
    return results


__all__ = ["DirectionalHDRIFT", "embed_block", "evaluate_modes"]
