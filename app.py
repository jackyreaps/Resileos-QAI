"""
FastAPI backend for Resileos-QAI.

Endpoints:
    /api/v1/verify_manifold   QD-TER bridge verification (RES-600/601/602)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from resileos.substrate.geometry import LowRankMetricHead  # noqa: E402
from resileos.substrate.reduction import VerifiableFEPReductionHead  # noqa: E402

app = FastAPI(title="Resileos-QAI")

HIDDEN_DIM = int(os.getenv("RESILEOS_HIDDEN_DIM", "128"))
KERNEL_DIM = int(os.getenv("RESILEOS_KERNEL_DIM", "1"))   # rank-1 per RES-600 §4


class SubstrateContainer:
    """Module-level persistent model singleton."""

    def __init__(self) -> None:
        torch.manual_seed(42)
        raw_kernel = torch.randn(HIDDEN_DIM, KERNEL_DIM)
        q_kernel, _ = torch.linalg.qr(raw_kernel)

        self.geo_head = LowRankMetricHead(hidden_dim=HIDDEN_DIM)
        self.fep_head = VerifiableFEPReductionHead(
            hidden_dim=HIDDEN_DIM, L_H_kernel=q_kernel, rank=1,
        )
        self.is_trained = False
        self.training_steps = 0


substrate_singleton = SubstrateContainer()


class VerificationRequest(BaseModel):
    hierarchical_states: list   # [1, T, L, D]
    velocity_direction: list    # [1, T, D]
    g_field_sequence: list      # [1, T, 1]


@app.post("/api/v1/verify_manifold")
def verify_manifold(payload: VerificationRequest):
    if not substrate_singleton.is_trained:
        raise HTTPException(
            status_code=400,
            detail=(
                "Substrate is UNTRAINED. "
                f"completed_steps={substrate_singleton.training_steps}."
            ),
        )
    try:
        h = torch.tensor(payload.hierarchical_states, dtype=torch.float32)
        x = torch.tensor(payload.velocity_direction, dtype=torch.float32)
        g = torch.tensor(payload.g_field_sequence, dtype=torch.float32)

        if h.dim() != 4 or h.size(0) != 1:
            raise ValueError(f"hierarchical_states must be [1, T, L, D], got {tuple(h.shape)}")
        trunk = h.mean(dim=2)     # [1, T, D]

        with torch.no_grad():
            _, geo_loss = substrate_singleton.geo_head(trunk, x)
            psi_s, fep_loss = substrate_singleton.fep_head(trunk, g)

        return {
            "status": "verified",
            "parallel_transport_penalty": float(geo_loss.item()),
            "fep_ode_alignment_loss": float(fep_loss.item()),
            "slow_subspace_trajectory": psi_s.squeeze(0).squeeze(-1).tolist(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"manifold error: {e}")


@app.get("/api/v1/substrate_stats")
def substrate_stats():
    return {
        "hidden_dim": HIDDEN_DIM,
        "kernel_dim": KERNEL_DIM,
        "is_trained": substrate_singleton.is_trained,
        "training_steps": substrate_singleton.training_steps,
        "bridge_locked": True,     # BridgeMetricHead raises NotImplementedError
    }
