"""Language pipeline.

Composes the modules into one callable:
    tokens -> codex.encode -> hv -> reshape (m, n) -> ResidualCore.step
    -> packet -> monitors -> reaper_pass on lat_s_k
    -> KuramotoField step from epsilon_from_monitors
    -> codex.cleanup at each position -> tokens

Read-only with respect to the classical core. The pipeline consumes the packet;
nothing writes back. Round-trip is the plumbing check. Reconstruction error is
reported separately as a diagnostic. No claim of prediction. No trained model.

Orientation contract (RES-304, RES-307):
    The oscillator field's dtheta signs carry directional commitment. When
    phi-compress contracts the rank, surviving oscillators keep their theta,
    omega, and dtheta sign. The dropped oscillators' coupling weight is
    redistributed among survivors. The field is rebuilt with random_start=False.

    The number of oscillators dropped is exactly old_r - new_r, where new_r
    is whatever contract_rank returns. Dropping a fixed count of one while
    contract_rank drops more leads to a W slice whose shape disagrees with
    the rebuilt field's r.
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
    phi_compress_warmup: int = 32
    phi_compress_min_R: float = 0.9
    basin_depth_max_spread: float = 0.5
    oscillator_kappa: float = 1.0
    oscillator_alpha: float = 0.5
    oscillator_dt: float = 0.1
    seed: int = 0

    def validate(self) -> None:
        if self.m * self.n != self.dim:
            raise ValueError(f"m*n ({self.m * self.n}) must equal dim ({self.dim})")
        if self.r > min(self.m, self.n):
            raise ValueError("r must be <= min(m, n)")
        if self.reaper_n_saved > self.r:
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
                m=cfg.m,
                n=cfg.n,
                r=cfg.r,
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
        self._last_R = 0.0
        self._compressions: list[int] = []
        self._orientation: Optional[np.ndarray] = None  # last known dtheta signs

    # ── φ-compress hook ────────────────────────────────────────────────
    def _should_compress(self) -> bool:
        if not self.cfg.phi_compress_enabled:
            return False
        if self._step_count < self.cfg.phi_compress_warmup:
            return False
        if self._last_R < self.cfg.phi_compress_min_R:
            return False
        if self.core.cfg.r <= self.cfg.phi_compress_min_rank:
            return False
        # RES-304 §2: don't contract if basin depth is below threshold.
        # Approximate basin depth by the field's phase spread relative
        # to the lock width. Large spread -> shallow basin -> don't drop rank.
        if self.field.r > 1:
            theta = self.field.theta
            spread = float(np.std(np.angle(np.exp(1j * theta))))
            if spread > self.cfg.basin_depth_max_spread:
                return False
        return True

    def _maybe_contract(self) -> None:
        if not self._should_compress():
            return
        old_r = self.core.cfg.r
        new_r = contract_rank(old_r, min_rank=self.cfg.phi_compress_min_rank)
        if new_r >= old_r:
            return

        # 1. Capture orientation BEFORE rebuild.
        #    evolution_oscillator.py: dtheta_i < 0 -> flip mask bit i.
        #    dtheta_i >= 0 -> keep mask bit i.
        #    Preserve that sign structure across contraction.
        theta_old = self.field.theta.copy()
        omega_old = self.field.omega.copy()
        theta_ref = float(np.angle(np.mean(np.exp(1j * theta_old))))
        dtheta_signs = np.sign(
            np.angle(np.exp(1j * (theta_old - theta_ref)))
        )
        dtheta_signs[dtheta_signs == 0] = 1.0  # tie-break like evolution_oscillator

        # 2. Drop exactly (old_r - new_r) oscillators, weakest orientation
        #    commitment first. contract_rank may drop more than one rank;
        #    keep must match new_r or the W slice will not square with the
        #    rebuilt field.
        n_drop = old_r - new_r
        order = np.argsort(np.abs(dtheta_signs))
        drop_set = set(int(i) for i in order[:n_drop])
        keep = [i for i in range(old_r) if i not in drop_set]
        assert len(keep) == new_r, (
            f"keep size {len(keep)} != new_r {new_r}"
        )

        # 3. Rebuild core and field.
        self.core = ResidualCore(
            contract_config(
                self.core.cfg, min_rank=self.cfg.phi_compress_min_rank
            ),
            seed=self.cfg.seed,
            non_conservative=True,
        )
        self.field = KuramotoField(
            r=new_r,
            ladder="golden_powers",
            kappa=self.cfg.oscillator_kappa,
            alpha=self.cfg.oscillator_alpha,
            dt=self.cfg.oscillator_dt,
            random_start=False,  # critical: no re-randomization
            seed=self.cfg.seed,
        )

        # 4. Transfer orientation: surviving oscillators keep theta, omega,
        #    and dtheta sign. Dropped oscillators' coupling weight is
        #    redistributed to keep mean kappa constant.
        self.field.theta = theta_old[keep].copy()
        self.field.omega = omega_old[keep].copy()
        W_old = self._W_osc
        W_new = W_old[np.ix_(keep, keep)].copy()
        if W_new.size > 0:
            W_new *= W_old.mean() / (W_new.mean() + 1e-12)
        self._W_osc = W_new

        # 5. Record orientation that survived.
        self._orientation = dtheta_signs[keep].copy()
        self._compressions.append(self._step_count)

    # ── step ───────────────────────────────────────────────────────────
    def step(self, tokens: list[int]) -> PipelineResult:
        if not tokens:
            raise ValueError("tokens must be non-empty")
        if len(tokens) > self.cfg.max_positions:
            raise ValueError(
                f"sequence length {len(tokens)} > max_positions "
                f"{self.cfg.max_positions}"
            )
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

        # 6. Reaper
        lat = np.abs(packet.lat_s_k.astype(np.float64))
        _, henad_idx, nexus_idx, fraction = reaper_pass(
            lat, n_saved=min(self.cfg.reaper_n_saved, lat.size)
        )

        # 7. Oscillator step
        self.field.step(epsilon=eps, W=self._W_osc)
        R = self.field.order_parameter()
        self._last_R = R

        # Update orientation from the live field for next contraction.
        if self.field.r > 1:
            theta = self.field.theta
            theta_ref = float(np.angle(np.mean(np.exp(1j * theta))))
            self._orientation = np.sign(
                np.angle(np.exp(1j * (theta - theta_ref)))
            )
            self._orientation[self._orientation == 0] = 1.0

        # 8. Gate state (report only)
        if R > 0.9:
            gate_state = "LOCKED"
        elif R < 0.3:
            gate_state = "EXPLORING"
        else:
            gate_state = "MIXED"

        # 9. Decode
        recovered = [self.codex.cleanup(hv, p) for p in range(len(tokens))]

        # 10. Reconstruction error
        W_hat = self.core.last_reconstruction
        if W_hat is None:
            recon_err = 1.0
        else:
            recon_err = float(
                np.linalg.norm(W - W_hat) / (np.linalg.norm(W) + 1e-12)
            )

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

    # ── introspection ──────────────────────────────────────────────────
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
    """One sequence per line, comma-separated integers.

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
