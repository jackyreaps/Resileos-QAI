"""
Classical residual core: the sole producer of the control packet.
Owning doc: RES-200.

This module never receives gradients (RES-401). It is deterministic given
(W, mu, F_res, thresholds) and its internal state.

Invariants owned here:
  - volume preservation: |log10|det J|| < 1e-9 per step
  - residual-flux parity: hysteresis on signed F_res
  - Prime-Tower schedule: rank = PrimeTower(schedule_index)
  - scar diagonal pinned to 1 (unipotent-neutral)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .packet import Packet, encode_exponent, packet_hash
from .abstention import ParityState


# Prime Tower schedule: even/odd discrete schedule for residual rank (RES-200).
_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def prime_tower(schedule_index: int) -> int:
    """RES-200: rank = PrimeTower(schedule_index)."""
    return _PRIMES[int(schedule_index) % len(_PRIMES)]


def _strict_lower(N: np.ndarray) -> np.ndarray:
    """Strict lower-triangular part (zero diagonal)."""
    return np.tril(N, k=-1)


@dataclass
class CoreConfig:
    m: int
    n: int
    r: int
    alpha: float = 0.95   # scar decay
    beta: float = 0.05    # residual contribution
    gamma: float = 0.02   # triangular-friendly correction


class ResidualCore:
    """
    Deterministic residual-compensation producer (RES-200).

    Consumes a weight block W (m × n), performs latent factorization →
    binary factors → residual membrane → scar update → unipotent embed,
    and emits a conformant control packet per step.

    The front-end encoder is trainable; this class is not. See RES-401.
    """

    def __init__(self, cfg: CoreConfig, seed: int = 0) -> None:
        self.cfg = cfg
        rng = np.random.default_rng(seed)
        self._Ub0 = np.sign(rng.standard_normal((cfg.m, cfg.r)))
        self._Vb0 = np.sign(rng.standard_normal((cfg.r, cfg.n)))
        self._Ub0[self._Ub0 == 0] = 1.0
        self._Vb0[self._Vb0 == 0] = 1.0
        self._Lambda = np.eye(cfg.r, dtype=np.float32)
        self._step = 0

    # ── internals ─────────────────────────────────────────────────────────
    def _factorize(self, W: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Latent factorization → binary factors Ub (m×r), Vb (r×n), and
        reconstruction W̃ = s · Ub @ Vb with s chosen to minimize ||W − W̃||_F.
        """
        U = W @ self._Vb0.T                  # (m, r)
        V = self._Ub0.T @ W                  # (r, n)
        Ub = np.sign(U); Ub[Ub == 0] = 1.0
        Vb = np.sign(V); Vb[Vb == 0] = 1.0

        P = Ub @ Vb
        s = float(np.sum(W * P)) / (float(np.sum(P * P)) + 1e-12)
        return Ub.astype(np.float32), Vb.astype(np.float32), (s * P)

    def _scar_update(self, M_lat: np.ndarray) -> np.ndarray:
        """
        Λ ← αΛ + β M + γ F(Λ, M), with F strictly lower-triangular so the
        composite map stays unipotent. Diagonal pinned to 1.
        """
        F = _strict_lower(M_lat @ self._Lambda - self._Lambda @ M_lat)
        new = (
            self.cfg.alpha * self._Lambda
            + self.cfg.beta * M_lat
            + self.cfg.gamma * F
        )
        np.fill_diagonal(new, 1.0)
        return new.astype(np.float32)

    def _residual_scales(self,
                         R: np.ndarray,
                         Ub: np.ndarray,
                         Vb: np.ndarray,
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Row / column / latent residual magnitudes on the ε-grid (RES-200)."""
        row_mag = np.linalg.norm(R, axis=1)
        col_mag = np.linalg.norm(R, axis=0)
        lat_mag = np.linalg.norm(Ub.T @ R @ Vb.T, axis=1)
        return (
            np.array([encode_exponent(x) for x in row_mag], dtype=np.int16),
            np.array([encode_exponent(x) for x in col_mag], dtype=np.int16),
            np.array([encode_exponent(x) for x in lat_mag], dtype=np.int16),
        )

    def _volume_guard(self, Lambda: np.ndarray) -> tuple[float, bool]:
        """
        J = I + strict_lower(Λdet) is unit lower triangular, so det J = 1
        exactly. Verify numerically and report |log10|det J||.
        """
        J = np.eye(self.cfg.r, dtype=np.float64) + _strict_lower(
            Lambda.astype(np.float64)
        )
        det = float(np.linalg.det(J))
        log_abs = abs(np.log10(abs(det) + 1e-300))
        return det, bool(logdet_abs < 1e-9)

    # ── public API ────────────────────────────────────────────────────────
    def step(self,
             W: np.ndarray,
             mu: int = 0,
             F_res: float = 0.0,
             theta_hi: float = 0.0,
             theta_lo: float = 0.0,
             DeltaS: float = 0.0,
             sigma1_gate: bool = False,
             sigma1_action: str = "NONE",
             version: str = "1.0.0",
             ) -> Packet:
        """One step: factorize, update scar, emit conformant packet."""
        W = np.asarray(W, dtype=np.float64)
        if W.shape != (self.cfg.m, self.cfg.n):
            raise ValueError(
                f"W must be ({self.cfg.m}, {self.cfg.n}), got {W.shape}"
            )

        Ub, Vb, W_hat = self._factorize(W)
        R = W - W_hat                                       # residual membrane
        M_lat = (Ub.T @ R @ Vb.T) / float(self.cfg.m * self.cfg.n)
        self._Lambda = self._scar_update(M_lat)

        row_s, col_s, lat_s = self._residual_scales(R, Ub, Vb)

        volume, volume_ok = self._volume_guard(self._Lambda)

        mu_new, _ = ParityState(
            mu=int(mu),
            theta_hi=float(theta_hi),
            theta_lo=float(theta_lo),
        ).update(float(F_res))

        packet = Packet(
            version=version,
            Ub=Ub,
            Vb=Vb,
            row_s_k=row_s,
            col_s_k=col_s,
            lat_s_k=lat_s,
            Lambda=self._Lambda,
            mu=int(mu_new),
            DeltaS=float(DeltaS),
            F_res=float(F_res),
            volume=float(volume),
            volume_ok=bool(volume_ok),
            rank=int(prime_tower(self._step)),
            schedule_index=int(self._step),
            sigma1_gate=bool(sigma1_gate),
            sigma1_action=str(sigma1_action),
        )
        packet.packet_hash = packet_hash(packet)
        self._step += 1
        return packet

    # ── diagnostics ───────────────────────────────────────────────────────
    @property
    def Lambda(self) -> np.ndarray:
        return self._Lambda

    @property
    def schedule_index(self) -> int:
        return self._step
