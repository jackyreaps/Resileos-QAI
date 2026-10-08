"""
Hybrid generative validation harness against declared (X, Y).
Owning doc: RES-402. Conformance rule: X and Y must be declared before run.

Sigma-1 gate is evaluated by default each step (RES-303). Consecutive
volume failures escalate through the gate to CLEANUP rather than falling
through the abstention machine to ABSTAIN.
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
        """RES-402 §conformance: no run without declared X, Y."""
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

    The sigma-1 gate owns volume-failure escalation: k consecutive
    volume_ok == False steps escalate to CLEANUP before the abstention
    machine is consulted.
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
            E_sigma=config.E_sigma,
            k=config.sigma1_k,
        )
        self.logs: list[dict[str, Any]] = []

    # ── routing ────────────────────────────────────────────────────────────
    def _route(self,
               packet: Any,
               scar_energy: float,
               sigma1_action: str | None) -> str:
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

    # ── per-step gate evaluation ───────────────────────────────────────────
    def _evaluate_sigma1(self,
                         packet: Any,
                         scar_energy: float,
                         step: int,
                         sigma1_fn: Callable[[Any, int], str | None] | None,
                         ) -> SigmaAction:
        get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))

        gate_action = self.sigma_gate.evaluate(
            scar_energy=scar_energy,
            mu=int(get("mu")),
            volume_ok=bool(get("volume_ok")),
        )

        # Optional external override for tests / custom schedules.
        if sigma1_fn is not None:
            override = sigma1_fn(packet, step)
            if override is not None:
                gate_action = SigmaAction(override)

        return gate_action

    # ── main run ───────────────────────────────────────────────────────────
    def run(self,
            packet_fn: Callable[[int, int], Any],
            x_fn: Callable[[int, int], np.ndarray],
            horizon_len: int,
            recon_err_fn: Callable[[Any], float],
            sigma1_fn: Callable[[Any, int], str | None] | None = None,
            ) -> dict[str, Any]:
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

                # Sigma-1 gate first (RES-303 precedence).
                gate_action = self._evaluate_sigma1(
                    packet=packet,
                    scar_energy=out["scar_energy"],
                    step=t,
                    sigma1_fn=sigma1_fn,
                )
                sigma1_arg = gate_action.value if gate_action != SigmaAction.NONE else None

                # Abstention machine (or sigma-1 result if it fired).
                state = self._route(packet, out["scar_energy"], sigma1_arg)

                # Optional REPULSE hold counter (RES-500 §1).
                if state == "REPULSE":
                    repulse_counter += 1
                    if self.cfg.repulse_hold > 0 and repulse_counter > self.cfg.repulse_hold:
                        state = "ABSTAIN"
                else:
                    repulse_counter = 0

                # B.3 §10 five-tuple + extras.
                self.logs.append({
                    "seed": seed,
                    "step": t,
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


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", default="report.json")
    args = p.parse_args()
    print(f"Loaded config: {args.config}")
    print(f"Would write report to: {args.out}")
    print("Replace with real packet/x generators before running.")
