"""Aggregate carrier for coupled EngineGroup features (Path B).

Small MLP mapping the 7-dim aggregate (R_shared, upper-tri coupling
matrix, per-engine mean F_res) to a modulation vector for a frozen
decoder.

Separate from `resileos.carrier.SubstrateCarrier`, which requires a full
RES-201 packet. The aggregate carrier reads only the aggregate features
that RES-319 measured as carrying signal (ΔMI_R ≈ +1.24, ΔMI_M ≈ +1.13).
Per-engine lat_s_k is deliberately excluded — RES-319 §3a confirmed it is
constant under the current drive path (Cause A: int16 exponent encoding
that quantizes), so including it adds noise dimensions.

Design notes:
    Zero-init output so training starts at zero modulation.
    Learnable `bias_scale` init 1.0; the scale learns its magnitude.
    `input_dim` defaults to 7 (N=3). Other N require matching changes to
    the feature builder.

Off states:
    No learned position structure. The bias is per-example, constant
    across all sequence positions.
    No embedding-bias head. Logit bias only. Embedding injection is a
    future ablation (RES-319 §5 open questions).
"""
from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
import torch
import torch.nn as nn


def _stable_hash(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:8], 16)


def _fact_drive(
    fact: tuple[str, str, str], n_engines: int, seed: int
) -> np.ndarray:
    """Deterministic per-fact drive vector."""
    h = _stable_hash("|".join(str(x) for x in fact))
    rng = np.random.default_rng(seed + (h % (2**31)))
    return rng.standard_normal(n_engines) * 0.5


def build_aggregate_features(
    facts: list[tuple[str, str, str]],
    n_engines: int = 3,
    kappa: float = 2.0,
    m: int = 8,
    r: int = 4,
    n_steps_per_fact: int = 10,
    seed: int = 0,
) -> np.ndarray:
    """Build (n_facts, input_dim) aggregate features.

    One fresh EngineGroup per fact, stepped `n_steps_per_fact` times with
    that fact's drive. Features are extracted from the final state.

    input_dim = 1 + N*(N-1)/2 + N
        R_shared           : 1
        upper-tri M        : N*(N-1)/2
        per-engine mean F_res : N

    For N=3: 1 + 3 + 3 = 7.
    """
    from resileos.core import CoreConfig
    from resileos.substrate.coupling import CouplingField
    from resileos.substrate.engine_group import EngineGroup

    n = int(n_engines)
    features = []
    for idx, fact in enumerate(facts):
        configs = [CoreConfig(m=m, n=m, r=r) for _ in range(n)]
        field = CouplingField(n_engines=n, kappa=kappa, seed=seed)
        group = EngineGroup(configs, field, seed=seed)

        drives = _fact_drive(fact, n, seed)
        Ws = [
            np.random.default_rng(seed + idx * n + i).standard_normal((m, m))
            for i in range(n)
        ]

        cp = None
        for _ in range(n_steps_per_fact):
            cp = group.step([w.copy() for w in Ws], drives=drives.copy())

        R = float(cp.R_shared)
        M = np.asarray(cp.coupling_matrix, dtype=np.float64)
        M_triu = M[np.triu_indices(n, k=1)]
        mean_F_res = np.array(
            [float(p.F_res) for p in cp.packets], dtype=np.float64
        )

        feat = np.concatenate([[R], M_triu, mean_F_res])
        features.append(feat)

    return np.stack(features).astype(np.float32)


class AggregateCarrier(nn.Module):
    """7 -> hidden -> 7 -> output. Zero-init output; learnable bias scale.

    Input  : (B, input_dim) float32
    Output : (B, output_dim) float32, meant to be added to logits as a
             per-example constant bias.
    """

    def __init__(
        self,
        input_dim: int = 7,
        output_dim: int = 151936,
        hidden_dim: int = 64,
        n_hidden_layers: int = 2,
    ) -> None:
        super().__init__()
        if input_dim < 1:
            raise ValueError("input_dim must be >= 1")
        if output_dim < 1:
            raise ValueError("output_dim must be >= 1")
        self.input_dim = int(input_dim)
        self.output_dim = int(output_dim)
        self.hidden_dim = int(hidden_dim)

        layers: list[nn.Module] = []
        in_dim = self.input_dim
        for _ in range(int(n_hidden_layers)):
            layers.append(nn.Linear(in_dim, self.hidden_dim))
            layers.append(nn.GELU())
            in_dim = self.hidden_dim
        layers.append(nn.Linear(in_dim, self.output_dim))
        self.net = nn.Sequential(*layers)

        # Zero-init last layer so the carrier starts as identity
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)
        self.bias_scale = nn.Parameter(torch.ones(()))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        if features.shape[-1] != self.input_dim:
            raise ValueError(
                f"features last dim {features.shape[-1]} != input_dim "
                f"{self.input_dim}"
            )
        out = self.net(features)
        return out * self.bias_scale

    def describe(self) -> dict:
        return {
            "input_dim": self.input_dim,
            "output_dim": self.output_dim,
            "hidden_dim": self.hidden_dim,
            "n_params": sum(p.numel() for p in self.parameters()),
            "n_trainable": sum(
                p.numel() for p in self.parameters() if p.requires_grad
            ),
        }


__all__ = [
    "AggregateCarrier",
    "build_aggregate_features",
    "_fact_drive",
    "_stable_hash",
]
