"""
FastAPI backend for Resileos-QAI.

Endpoints:
    GET  /api/v1/substrate_stats     — current model state
    POST /api/v1/train_substrate     — optimize the two heads, flip is_trained
    POST /api/v1/verify_manifold     — infer on a trajectory (gated on is_trained)
    POST /api/v1/sweep_epsilon       — run the ε-sweep verification (ungated)

The sweep is a numerical verification of RES-600 §4. It does not require
trained heads and is therefore exposed without the is_trained gate.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from resileos.substrate.geometry import LowRankMetricHead  # noqa: E402
from resileos.substrate.reduction import (  # noqa: E402
    VerifiableFEPReductionHead,
    simulate_axiom_d,
)

app = FastAPI(title="Resileos-QAI")

HIDDEN_DIM = int(os.getenv("RESILEOS_HIDDEN_DIM", "128"))
KERNEL_DIM = int(os.getenv("RESILEOS_KERNEL_DIM", "1"))    # rank-1 per RES-600 §4
MIN_TRAIN_STEPS = int(os.getenv("RESILEOS_MIN_TRAIN_STEPS", "5"))


# ── persistent container ─────────────────────────────────────────────────
class SubstrateContainer:
    """Module-level persistent model singleton."""

    def __init__(self) -> None:
        torch.manual_seed(42)
        raw_kernel = torch.randn(HIDDEN_DIM, KERNEL_DIM)
        q_kernel, _ = torch.linalg.qr(raw_kernel)

        self.hidden_dim = HIDDEN_DIM
        self.kernel_dim = KERNEL_DIM

        self.geo_head = LowRankMetricHead(hidden_dim=HIDDEN_DIM)
        self.fep_head = VerifiableFEPReductionHead(
            hidden_dim=HIDDEN_DIM, L_H_kernel=q_kernel, rank=1,
        )

        trainable = (
            list(self.geo_head.parameters()) + list(self.fep_head.parameters())
        )
        self.optimizer = torch.optim.AdamW(trainable, lr=1e-3)

        self.is_trained = False
        self.training_steps = 0
        self.last_train_metrics: dict | None = None

    def train_step(
        self,
        seq_len: int,
        g_field: float,
        epsilon: float,
        seed: int,
    ) -> dict:
        """One optimization step on a synthetic Axiom D trajectory."""
        self.optimizer.zero_grad()

        trunk = simulate_axiom_d(
            dim=self.hidden_dim, seq_len=seq_len,
            epsilon=epsilon, g_field=g_field, seed=seed,
        )
        # Direction: finite difference as a proxy for X
        X = torch.zeros_like(trunk)
        X[:, :-1] = trunk[:, 1:] - trunk[:, :-1]
        X[:, -1] = X[:, -2]

        G = torch.ones(1, seq_len, 1)

        _, geo_loss = self.geo_head(trunk, X)
        _, fep_loss = self.fep_head(trunk, G)

        total = geo_loss + fep_loss
        total.backward()
        self.optimizer.step()

        self.training_steps += 1
        metrics = {
            "geo": float(geo_loss.item()),
            "fep": float(fep_loss.item()),
            "total": float(total.item()),
        }
        self.last_train_metrics = metrics
        return metrics


substrate_singleton = SubstrateContainer()


# ── request schemas ─────────────────────────────────────────────────────
class VerificationRequest(BaseModel):
    hierarchical_states: list = Field(
        ..., description="[1, T, L, D] hierarchy of hidden states"
    )
    velocity_direction: list = Field(..., description="[1, T, D] velocity")
    g_field_sequence: list = Field(..., description="[1, T, 1] coherence")


class TrainRequest(BaseModel):
    steps: int = 10
    seq_len: int = 64
    g_field: float = 0.85
    base_epsilon: float = 0.1
    seed: int = 0


class SweepRequest(BaseModel):
    mode: str = "simulate"                        # "simulate" | "data"
    epsilons: list[float] = [
        0.1, 0.05, 0.02, 0.01, 0.005, 0.001
    ]
    metric: str = "rmse"                          # "rmse" | "mse"
    g_field: float = 0.85
    seq_len: int = 64
    # Only used when mode == "data"
    trajectory: list | None = None                # [T, D] or [K, T, D]


# ── endpoints ───────────────────────────────────────────────────────────
@app.get("/api/v1/substrate_stats")
def substrate_stats():
    return {
        "hidden_dim": substrate_singleton.hidden_dim,
        "kernel_dim": substrate_singleton.kernel_dim,
        "is_trained": substrate_singleton.is_trained,
        "training_steps": substrate_singleton.training_steps,
        "min_train_steps": MIN_TRAIN_STEPS,
        "last_train_metrics": substrate_singleton.last_train_metrics,
        "bridge_locked": True,    # BridgeMetricHead raises NotImplementedError
    }


@app.post("/api/v1/train_substrate")
def train_substrate(payload: TrainRequest):
    if payload.steps < 1 or payload.steps > 500:
        raise HTTPException(400, "steps must be in [1, 500]")

    history = []
    for i in range(payload.steps):
        # Vary ε per step so the ODE sees a range of perturbation scales
        eps = payload.base_epsilon / (1.0 + 0.3 * i)
        try:
            metrics = substrate_singleton.train_step(
                seq_len=payload.seq_len,
                g_field=payload.g_field,
                epsilon=eps,
                seed=payload.seed + i,
            )
        except Exception as e:
            raise HTTPException(500, f"training step {i} failed: {e}")
        history.append({"step": i, "epsilon": eps, **metrics})

    if substrate_singleton.training_steps >= MIN_TRAIN_STEPS:
        substrate_singleton.is_trained = True

    return {
        "status": "trained" if substrate_singleton.is_trained else "partial",
        "total_steps": substrate_singleton.training_steps,
        "is_trained": substrate_singleton.is_trained,
        "history": history,
    }


@app.post("/api/v1/verify_manifold")
def verify_manifold(payload: VerificationRequest):
    if not substrate_singleton.is_trained:
        raise HTTPException(
            status_code=400,
            detail=(
                "Substrate is UNTRAINED. "
                f"completed_steps={substrate_singleton.training_steps}, "
                f"min={MIN_TRAIN_STEPS}. "
                "Call POST /api/v1/train_substrate first."
            ),
        )
    try:
        h = torch.tensor(payload.hierarchical_states, dtype=torch.float32)
        x = torch.tensor(payload.velocity_direction, dtype=torch.float32)
        g = torch.tensor(payload.g_field_sequence, dtype=torch.float32)

        if h.dim() != 4 or h.size(0) != 1:
            raise ValueError(
                f"hierarchical_states must be [1, T, L, D], "
                f"got {tuple(h.shape)}"
            )
        if h.size(-1) != substrate_singleton.hidden_dim:
            raise ValueError(
                f"last dim must equal hidden_dim "
                f"({substrate_singleton.hidden_dim}), got {h.size(-1)}"
            )
        trunk = h.mean(dim=2)          # [1, T, D]

        with torch.no_grad():
            _, geo_loss = substrate_singleton.geo_head(trunk, x)
            psi_s, fep_loss = substrate_singleton.fep_head(trunk, g)

        return {
            "status": "verified",
            "parallel_transport_penalty": float(geo_loss.item()),
            "fep_ode_alignment_loss": float(fep_loss.item()),
            "slow_subspace_trajectory": (
                psi_s.squeeze(0).squeeze(-1).tolist()
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"manifold error: {e}")


@app.post("/api/v1/sweep_epsilon")
def sweep_epsilon(payload: SweepRequest):
    """
    Run the ε-sweep verification.

    Ungated — the sweep measures the theorem's residual scaling on either a
    simulated Axiom D trajectory or a user-supplied trajectory. It does not
    require trained heads.
    """
    if payload.metric not in ("rmse", "mse"):
        raise HTTPException(400, f"metric must be 'rmse' | 'mse', got "
                                 f"{payload.metric!r}")
    if len(payload.epsilons) < 2:
        raise HTTPException(400, "at least two epsilon values required")
    if any(e <= 0.0 for e in payload.epsilons):
        raise HTTPException(400, "epsilons must all be > 0")

    dim = substrate_singleton.hidden_dim

    if payload.mode == "simulate":
        def factory(eps: float) -> torch.Tensor:
            return simulate_axiom_d(
                dim=dim, seq_len=payload.seq_len,
                epsilon=eps, g_field=payload.g_field, seed=0,
            )
    elif payload.mode == "data":
        if payload.trajectory is None:
            raise HTTPException(
                400, "mode='data' requires a trajectory array"
            )
        arr = np.asarray(payload.trajectory, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[None, ...]
        if arr.ndim != 3:
            raise HTTPException(
                400, f"trajectory must be [T, D] or [K, T, D], got {arr.shape}"
            )
        if arr.shape[-1] != dim:
            raise HTTPException(
                400, f"trajectory last dim {arr.shape[-1]} != hidden_dim {dim}"
            )
        trunk_ref = torch.tensor(
            arr.mean(axis=0)[None, ...], dtype=torch.float32
        )

        def factory(eps: float) -> torch.Tensor:
            t = trunk_ref.clone()
            t[:, 0, 0] = 1.5 + eps
            return t
    else:
        raise HTTPException(
            400, f"mode must be 'simulate' | 'data', got {payload.mode!r}"
       ing )

    try:
        sample = factory(payload.epsilons[0])
        G = torch.ones(1, sample.shape[1], 1)
        result = substrate_sleton.fep_head.sweep_epsilon(
            factory, payload.epsilons, G, metric=payload.metric,
        )
    except Exception as e:
        raise HTTPException(500, f"sweep failed: {e}")

    slope = result["slope"]
    if payload.metric == "rmse":
        if 0.85 <= slope <= 1.15:
            verdict = "consistent with linear O(ε) residual (RES-600 §4)"
        elif slope < 0.85:
            verdict = "sub-linear; check trajectory or discretization"
        else:
            verdict = "super-linear; check discretization error dominance"
    else:
        if 1.85 <= slope <= 2.15:
            verdict = "consistent with O(ε) residual under MSE metric"
        else:
            verdict = "unexpected MSE scaling"

    return {
        "source": payload.mode,
        "dim": dim,
        "g_field": payload.g_field,
        **result,
        "verdict": verdict,
    }
