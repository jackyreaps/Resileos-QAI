"""
Classical residual core: the sole producer of the control packet.
Owning doc: RES-200.

Never receives gradients (RES-401). Deterministic given (W, mu, F_res,
thresholds) and internal state.

Volume-preservation invariant:
    J = diag(D) + strict_lower(Lambda), with det(D) = 1.
    det(J) = det(D) = 1 exactly.
    This reduces to the original I + strict_lower(Lambda) case when
    D = I (conservative mode).

The optional NonConservativeOperator evolves D from monitors. See
`src/resileos/substrate/nonconservative.py` and RES-200 §extension.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .packet import Packet, encode_exponent, packet_hash
from .abstention import ParityState
from .substrate.nonconservative import NonConservativeOperator


_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def prime_tower(schedule_index: int) -> int:
    return _PRIMES[int(schedule_index) % len(_PRIMES)]


def _strict_lower(N: np.ndarray) -> np.ndarray:
    return np.tril(N, k=-1)


@dataclass
class CoreConfig:
    m: int
    n: int
    r: int
    alpha: float = 0.95
    beta: float = 0.05
    gamma: float = 0.02


class ResidualCore:
    """
    Deterministic residual-compensation producer (RES-200).

    Optional keyword arguments:
        non_conservative      enable the non-conservative operator
        nc_gamma_max          max |g_i| deviation in log space
        nc_phase_max          max |theta_i| in radians
        nc_decay              smoothing on g (larger = slower response)
    """

    def __init__(self, cfg: CoreConfig, seed: int = 0,
                 non_conservative: bool = False,
                 nc_gamma_max: float = 0.5,
                 nc_phase_max: float = 0.4,
                 nc_decay: float = 0.9) -> None:
        self.cfg = cfg
        rng = np.random.default_rng(seed)
        self._Ub0 = np.sign(rng.standard_normal((cfg.m, cfg.r)))
        self._Vb0 = np.sign(rng.standard_normal((cfg.r, cfg.n)))
        self._Ub0[self._Ub0 == 0] = 1.0
        self._Vb0[self._Vb0 == 0] = 1.0
        self._Lambda = np.eye(cfg.r, dtype=np.float32)
        self._step = 0
        self._nonconservative = NonConservativeOperator(
            r=cfg.r,
            mode="non-conservative" if non_conservative else "conservative",
            gamma_max=nc_gamma_max,
            phase_max=nc_phase_max,
            decay=nc_decay,
        )

    # ── internals ─────────────────────────────────────────────────────
    def _factorize(self, W):
        U = W @ self._Vb0.T
        V = self._Ub0.T @ W
        Ub = np.sign(U); Ub[Ub == 0] = 1.0
        Vb = np.sign(V); Vb[Vb == 0] = 1.0
        return Ub.astype(np.float32), Vb.astype(np.float32)

    def _scar_update(self, M_lat, F_res: float,
                     DeltaS: float, mu: int) -> np.ndarray:
        # Update the operator state from monitors first.
        self._nonconservative.update(F_res=F_res, DeltaS=DeltaS, mu=mu)
        # Effective matrix used by the scar dynamics.
        D = self._nonconservative.diagonal()
        Lambda_eff = np.diag(D) + _strict_lower(
            self._Lambda.astype(np.complex128))
        # Original scar update, based on the effective Lambda.
        F = _strict_lower(M_lat @ Lambda_eff - Lambda_eff @ M_lat)
        new = (self.cfg.alpha * self._Lambda
               + self.cfg.beta * M_lat
               + self.cfg.gamma * F.real)
        np.fill_diagonal(new, 1.0)
        return new.astype(np.float32)

    def _residual_scales(self, R, Ub, Vb):
        row_mag = np.linalg.norm(R, axis=1)
        col_mag = np.linalg.norm(R, axis=0)
        lat_mag = np.linalg.norm(Ub.T @ R @ Vb.T, axis=1)
        return (
            np.array([encode_exponent(x) for x in row_mag], dtype=np.int16),
            np.array([encode_exponent(x) for x in col_mag], dtype=np.int16),
            np.array([encode_exponent(x) for x in lat_mag], dtype=np.int16),
        )

    def _volume_guard(self, Lambda):
        """
        J = diag(D) + strict_lower(Lambda). By construction
        det(J) = prod(D) = 1 exactly, whatever Lambda is.

        In conservative mode (D = I), this reduces to det(I + strict_lower)
        = 1. The guard is a numerical check on the constraint, not on
        Lambda. See OscGraph.det_one_add_strictLower for the acyclic
        case, generalized to diag(D) here.
        """
        J = self._nonconservative.effective_matrix(Lambda)
        det = complex(np.linalg.det(J))
        log_abs = abs(np.log10(abs(det) + 1e-300))
        return det, bool(log_abs < 1e-9)

    # ── public API ────────────────────────────────────────────────────
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
             factors=None) -> Packet:
        """One step: factorize, update scar, emit conformant packet."""
        W = np.asarray(W, dtype=np.float64)
        if W.shape != (self.cfg.m, self.cfg.n):
            raise ValueError(
                f"W must be ({self.cfg.m}, {self.cfg.n}), got {W.shape}")

        if factors is not None:
            Ub_ext, Vb_ext = factors
            Ub = np.asarray(Ub_ext, dtype=np.float32)
            Vb = np.asarray(Vb_ext, dtype=np.float32)
            if Ub.shape != (self.cfg.m, self.cfg.r) or \
               Vb.shape != (self.cfg.r, self.cfg.n):
                raise ValueError(
                    f"factors shape mismatch: Ub {Ub.shape}, Vb {Vb.shape}")
        else:
            Ub, Vb = self._factorize(W)

        P = Ub @ Vb
        s = float(np.sum(W * P)) / (float(np.sum(P * P)) + 1e-12)
        W_hat = s * P
        R = W - W_hat
        M_lat = (Ub.T @ R @ Vb.T) / float(self.cfg.m * self.cfg.n)

        self._Lambda = self._scar_update(M_lat, F_res=F_res,
                                         DeltaS=DeltaS, mu=int(mu))

        row_s, col_s, lat_s = self._residual_scales(R, Ub, Vb)
        volume, volume_ok = self._volume_guard(self._Lambda)
        D = self._nonconservative.diagonal()

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
            volume=float(abs(volume)),
            volume_ok=bool(volume_ok),
            rank=int(prime_tower(self._step)),
            schedule_index=int(self._step),
            sigma1_gate=bool(sigma1_gate),
            sigma1_action=str(sigma1_action),
            D=D.astype(np.complex128),
        )
        packet.packet_hash = packet_hash(packet)
        self._step += 1
        return packet

    # ── diagnostics ───────────────────────────────────────────────────
    @property
    def Lambda(self) -> np.ndarray:
        return self._Lambda

    @property
    def schedule_index(self) -> int:
        return self._step

    @property
    def D(self) -> np.ndarray:
        return self._nonconservative.diagonal()

    @property
    def non_conservative_mode(self) -> bool:
        return self._nonconservative.mode == "non-conservative"
