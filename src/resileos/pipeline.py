"""
Language pipeline.

Composes the modules into one callable:

    tokens -> codex.encode -> hv
           -> reshape (m, n) -> ResidualCore.step -> packet
           -> monitors
           -> reaper_pass on lat_s_k
           -> KuramotoField step from epsilon_from_monitors
           -> codex.cleanup at each position -> tokens

Read-only with respect to the classical core. The pipeline consumes
the packet; nothing writes back.

Round-trip is the plumbing check. Reconstruction error is reported
separately as a diagnostic. No claim of prediction. No trained model.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .codex import PhiPhaseCodex
from .core import CoreConfig, ResidualCore
from .monitors import epsilon_from_monitors
from .phi_compress import contract_rank, contract_config
from .reaper import reaper_pass
from .substrate.oscillator import KuramotoField


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    dim: int = 256
    vocab_size: int = 64
    max_positions: int = 64
    m: int = 16
    n: int = 16
    r: int = 8
    n_residual_layers: int = 4
    reaper_n_saved: int = 8
    phi_compress_enabled: bool = False
    phi_compress_min_rank: int = 4
    oscillator_kappa: float = 1.0
    oscillator_alpha: float = 0.5
    oscillator_dt: float = 0.1
    seed: int = 0

    def validate(self) -> None:
        if self.m * self.n != self.dim:
            raise ValueError(
                f"m*n ({self.m * self.n}) must equal dim ({self.dim})")
        if self.r > min(self.m, self.n):
            raise ValueError("r must be <= min(m, n)")
        if self.reaper_n_saved > self.r:
            # Reaper will run on lat_s_k which has length r.
            # n_saved larger than r means no harvesting happens.
            pass

    @classmethod
    def from_json(cls, path: str | Path) -> "PipelineConfig":
        raw = json.loads(Path(path).read_text())
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in valid})

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ── result ──────────────────────────────────────────────────────────────
@dataclass
class PipelineResult:
    input_tokens: list[int]
    recovered: list[int]
    reaper_fraction: float
    nexus_count: int
    henad_count: int
    rank_used: int
    order_parameter: float
    epsilon: float
    gate_state: str
    reconstruction_rel_error: float

    def to_dict(self) -> dict:
        return {
            "input_tokens": list(self.input_tokens),
            "recovered": list(self.recovered),
            "reaper_fraction": float(self.reaper_fraction),
            "nexus_count": int(self.nexus_count),
            "henad_count": int(self.henad_count),
            "rank_used": int(self.rank_used),
            "order_parameter": float(self.order_parameter),
            "epsilon": float(self.epsilon),
            "gate_state": self.gate_state,
            "reconstruction_rel_error": float(self.reconstruction_rel_error),
        }

    @property
    def recovered_exactly(self) -> bool:
        return self.input_tokens == self.recovered


# ── pipeline ────────────────────────────────────────────────────────────
class LanguagePipeline:

    def __init__(self, cfg: PipelineConfig) -> None:
        cfg.validate()
        self.cfg = cfg
        self.codex = PhiPhaseCodex(
            vocab_size=cfg.vocab_size,
            dim=cfg.dim,
            max_positions=cfg.max_positions,
        )
        self.core = ResidualCore(
            CoreConfig(
                m=cfg.m, n=cfg.n, r=cfg.r,
                n_residual_layers=cfg.n_residual_layers,
            ),
            seed=cfg.seed,
            non_conservative=True,
        )
        self.field = KuramotoField(
            r=cfg.r,
            ladder="golden_powers",
            kappa=cfg.oscillator_kappa,
            alpha=cfg.oscillator_alpha,
            dt=cfg.oscillator_dt,
            random_start=True,
            seed=cfg.seed,
        )
        self._W_osc = np.ones((cfg.r, cfg.r)) - np.eye(cfg.r)

        self._step_count = 0
        self._last_R = 1.0
        self._compressions: list[int] = []

    # ── φ-compress hook ─────────────────────────────────────────────
    def _maybe_contract(self) -> None:
        """
        If enabled and the previous step's order parameter was locked,
        contract the residual rank by one φ step. Rebuilds the core
        with the new rank; original core is discarded.
        """
        if not self.cfg.phi_compress_enabled:
            return
        if self._last_R < 0.9:
            return
        if self.core.cfg.r <= self.cfg.phi_compress_min_rank:
            return
        new_r = contract_rank(self.core.cfg.r,
                              min_rank=self.cfg.phi_compress_min_rank)
        if new_r >= self.core.cfg.r:
            return
        self.core = ResidualCore(
            contract_config(self.core.cfg,
                            min_rank=self.cfg.phi_compress_min_rank),
            seed=self.cfg.seed,
            non_conservative=True,
        )
        # Rebuild oscillator field to match new rank
        self.field = KuramotoField(
            r=new_r,
            ladder="golden_powers",
            kappa=self.cfg.oscillator_kappa,
            alpha=self.cfg.oscillator_alpha,
            dt=self.cfg.oscillator_dt,
            random_start=True,
            seed=self.cfg.seed,
        )
        self._W_osc = np.ones((new_r, new_r)) - np.eye(new_r)
        self._compressions.append(self._step_count)

    # ── step ─────────────────────────────────────────────────────────
    def step(self, tokens: list[int]) -> PipelineResult:
        if not tokens:
            raise ValueError("tokens must be non-empty")
        if len(tokens) > self.cfg.max_positions:
            raise ValueError(
                f"sequence length {len(tokens)} > max_positions "
                f"{self.cfg.max_positions}")
        for t in tokens:
            if not (0 <= int(t) < self.cfg.vocab_size):
                raise ValueError(f"token {t} out of vocab range")

        self._maybe_contract()

        # 1. Encode tokens to a complex hypervector
        hv = self.codex.encode(tokens)

        # 2. Reshape real part into the core's input matrix
        W = np.real(hv).reshape(self.cfg.m, self.cfg.n).astype(np.float64)

        # 3. Drive from the input itself
        F_res = float(np.mean(np.abs(W)))
        DeltaS = float(1.0 / (1.0 + np.linalg.norm(W)))
        mu = int(self._step_count % 2)

        # 4. Core step
        packet = self.core.step(W, mu=mu, F_res=F_res, DeltaS=DeltaS)

        # 5. Monitors
        bundle = self.core.monitors()
        eps = epsilon_from_monitors(bundle) if bundle is not None else 1.0

        # 6. Reaper on the packet's latent exponents
        lat = np.abs(packet.lat_s_k.astype(np.float64))
        _, henad_idx, nexus_idx, fraction = reaper_pass(
            lat, n_saved=min(self.cfg.reaper_n_saved, lat.size))

        # 7. Oscillator step
        self.field.step(epsilon=eps, W=self._W_osc)
        R = self.field.order_parameter()
        self._last_R = R

        # 8. Gate state (report only)
        if R > 0.9:
            gate_state = "LOCKED"
        elif R < 0.3:
            gate_state = "EXPLORING"
        else:
            gate_state = "MIXED"

        # 9. Decode each position from the original hv
        recovered = [self.codex.cleanup(hv, p) for p in range(len(tokens))]

        # 10. Reconstruction error (diagnostic)
        W_hat = self.core.last_reconstruction
        if W_hat is None:
            recon_err = 1.0
        else:
            recon_err = float(
                np.linalg.norm(W - W_hat) / (np.linalg.norm(W) + 1e-12))

        self._step_count += 1

        return PipelineResult(
            input_tokens=list(tokens),
            recovered=[int(x) if x is not None else -1 for x in recovered],
            reaper_fraction=float(fraction),
            nexus_count=int(nexus_idx.size),
            henad_count=int(henad_idx.size),
            rank_used=int(self.core.cfg.r),
            order_parameter=float(R),
            epsilon=float(eps),
            gate_state=gate_state,
            reconstruction_rel_error=recon_err,
        )

    # ── introspection ────────────────────────────────────────────────
    def stats(self) -> dict:
        return {
            "step_count": int(self._step_count),
            "compressions": list(self._compressions),
            "current_rank": int(self.core.cfg.r),
            "last_R": float(self._last_R),
            "field_r": int(self.field.r),
        }


# ── corpus loader ───────────────────────────────────────────────────────
def load_corpus(path: str | Path) -> list[list[int]]:
    """
    One sequence per line, comma-separated integers.
    Blank lines and lines starting with '#' are ignored.
    """
    seqs: list[list[int]] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        seqs.append([int(x) for x in line.split(",")])
    return seqs


__all__ = [
    "PipelineConfig",
    "PipelineResult",
    "LanguagePipeline",
    "load_corpus",
]
