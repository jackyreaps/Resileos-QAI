"""
Hybrid generative validation harness against declared (X, Y).
Owning doc: RES-402. Conformance rule: X and Y must be declared before run.

Sigma-1 gate is evaluated by default each step (RES-303). Consecutive
volume failures escalate through the gate to CLEANUP rather than falling
through the abstention machine to ABSTAIN.

Target selection: the caller supplies target_fn(seed, step, packet, x_enc).
If not supplied, falls back to x_enc + 1% white noise (unpassable; kept only
for backward compatibility with prior reports).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .adapter import HDRIFTAdapter
from .abstention import AbstentionInputs, AbstentionThresholds, route_signals
from .sigma import SigmaGate, SigmaAction


@dataclass(frozen=True)
class RunConfig:
    packet_version: str
    dim: int
    seeds: Any
    N_warm: int
    E_sat: float
    E_sigma: float
    tau_sat: float
    tau_low: float
    sigma1_k: int
    X: float
    Y: int
    seed_list: tuple[int, ...]
    repulse_hold: int = 0
    volume_escalation: str = "sigma1_CLEANUP"
    shift_monitor: dict[str, Any] = field(default_factory=dict)
    scar_var_floor: float = 0.0
    deltaS_range_floor: float = 0.0
    drift_ratio_floor: float = 1e-3

    def assert_declared(self) -> None:
        if self.X is None or self.Y is None:
            raise ValueError(
                "RunConfig non-conformant: X and Y must be declared before execution."
            )


def flat_nrmse(targets: np.ndarray, predictions: np.ndarray) -> float:
    err = targets - predictions
    rmse = float(np.sqrt(np.mean(err ** 2)))
    span = float(np.ptp(targets)) + 1e-12
    return rmse / span


def horizon(errors: np.ndarray, tol: float) -> int:
    over = np.where(errors > tol)[0]
    return int(over[0]) if over.size else int(errors.size)


class HybridValidator:
    """
    Runs the adapter over a declared seed list, applies the sigma-1 gate
    (RES-303) and the abstention state machine (RES-302) each step, and
    reports (X, Y) conformance per RES-402.
    """

    def __init__(self,
                 config: RunConfig,
                 adapter: HDRIFTAdapter,
                 thresholds: AbstentionThresholds,
                 sigma_gate: SigmaGate | None = None) -> None:
        config.assert_declared()
        self.cfg = config
        self.adapter = adapter
        self.thresholds = thresholds
        self.sigma_gate = sigma_gate or SigmaGate(
            E_sigma=config.E_sigma, k=config.sigma1_k,
        )
        self.logs: list[dict[str, Any]] = []

    def _route(self, packet, scar_energy, sigma1_action):
        get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))
        return route_signals(
            AbstentionInputs(
                DeltaS=float(get("DeltaS")),
                mu=int(get("mu")),
                scar_energy=scar_energy,
                volume_ok=bool(get("volume_ok")),
            ),
            self.thresholds,
            sigma1_action,
        )

    def _evaluate_sigma1(self, packet, scar_energy, step, sigma1_fn):
        get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))
        gate_action = self.sigma_gate.evaluate(
            scar_energy=scar_energy,
            mu=int(get("mu")),
            volume_ok=bool(get("volume_ok")),
        )
        if sigma1_fn is not None:
            override = sigma1_fn(packet, step)
            if override is not None:
                gate_action = SigmaAction(override)
        return gate_action

    def run(self,
            packet_fn: Callable[[int, int], Any],
            x_fn: Callable[[int, int], np.ndarray],
            horizon_len: int,
            recon_err_fn: Callable[[Any], float],
            sigma1_fn: Callable[[Any, int], str | None] | None = None,
            target_fn: Callable[[int, int, Any, np.ndarray], np.ndarray] | None = None,
            ) -> dict[str, Any]:
        """
        target_fn(seed, step, packet, x_enc) -> np.ndarray
            The prediction target for this step. If None, defaults to
            x_enc + 1% white noise (unpassable; kept for compat).
        """
        per_seed = []
        for seed in self.cfg.seed_list:
            errs_h = np.zeros(horizon_len)
            errs_f = np.zeros(horizon_len)
            repulse_counter = 0

            for t in range(horizon_len):
                packet = packet_fn(seed, t)
                x_enc = x_fn(seed, t)
                out = self.adapter.step(packet, x_enc)

                get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))

                gate_action = self._evaluate_sigma1(
                    packet, out["scar_energy"], t, sigma1_fn,
                )
                sigma1_arg = gate_action.value if gate_action != SigmaAction.NONE else None
                state = self._route(packet, out["scar_energy"], sigma1_arg)

                if state == "REPULSE":
                    repulse_counter += 1
                    if self.cfg.repulse_hold > 0 and repulse_counter > self.cfg.repulse_hold:
                        state = "ABSTAIN"
                else:
                    repulse_counter = 0

                self.logs.append({
                    "seed": seed, "step": t,
                    "reconstruction_rel_error": float(recon_err_fn(packet)),
                    "scar_energy": float(out["scar_energy"]),
                    "DeltaS": float(get("DeltaS")),
                    "mu": int(get("mu")),
                    "logdetJ_abs": float(abs(np.log10(abs(float(get("volume"))) + 1e-300))),
                    "F_res": float(get("F_res")),
                    "sigma1_gate": bool(gate_action != SigmaAction.NONE),
                    "sigma1_action": str(gate_action.value),
                    "gate_state": state,
                    "drift_ratio": float(out["ratio"]),
                })

                # ── target selection ───────────────────────────────────
                if target_fn is not None:
                    target = target_fn(seed, t, packet, x_enc)
                else:
                    target = x_enc + 0.01 * np.random.default_rng(
                        seed * 1000 + t
                    ).standard_normal(x_enc.shape)

                errs_h[t] = np.linalg.norm(x_enc + out["drift"] - target)
                errs_f[t] = np.linalg.norm(x_enc - target)

            nrmse_h = flat_nrmse(np.zeros_like(errs_h), errs_h)
            nrmse_f = flat_nrmse(np.zeros_like(errs_f), errs_f)
            per_seed.append({
                "seed": seed,
                "nrmse_hybrid": float(nrmse_h),
                "nrmse_flat": float(nrmse_f),
                "nrmse_reduction_pct": float(100.0 * (nrmse_f - nrmse_h) / (nrmse_f + 1e-12)),
                "horizon_hybrid": int(horizon(errs_h, 1e-2)),
                "horizon_flat": int(horizon(errs_f, 1e-2)),
            })
            per_seed[-1]["horizon_extension"] = (
                per_seed[-1]["horizon_hybrid"] - per_seed[-1]["horizon_flat"]
            )

        red = np.array([r["nrmse_reduction_pct"] for r in per_seed])
        ext = np.array([r["horizon_extension"] for r in per_seed])

        return {
            "run_config": (
                asdict(self.cfg)
                if hasattr(self.cfg, "__dataclass_fields__")
                else self.cfg.__dict__
            ),
            "per_seed": per_seed,
            "aggregate": {
                "nrmse_reduction_mean_pct": float(np.mean(red)),
                "nrmse_reduction_std_pct": float(np.std(red)),
                "horizon_extension_mean": float(np.mean(ext)),
                "horizon_extension_std": float(np.std(ext)),
            },
            "conformant": bool(
                np.mean(red) >= self.cfg.X and np.mean(ext) >= self.cfg.Y
            ),
            "step_log": self.logs,
        }


def save_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, indent=2, default=float))
