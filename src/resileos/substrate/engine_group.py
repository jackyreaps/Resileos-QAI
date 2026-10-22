"""Engine group composition (RES-318).

N residual cores share one `CouplingField`. Their monitors are coupled
through the cross terms in RES-318 §5. Each step emits one
`CoupledPacket` carrying all N packets plus the shared field state.

Design:
    - Each engine has its own `ResidualCore` with a distinct seed
      derived from the group seed.
    - The `CouplingField` is stepped first (external drive), then the
      per-engine cross terms are computed from the resulting phase
      differences, then each core steps with the adjusted monitors.
    - The cross terms use the *previous* step's own monitors. The
      group tracks them as state. On the first step, defaults are used.
    - `monitors_own` may be supplied explicitly for external control
      (e.g. from a real probe). If None, the previous step's values
      are used.

Off states (explicit):
    trainable          off. No parameters, no gradients.
    packet-level fuse  off. CoupledPacket wraps N packets; it does not
                       merge them into one.
    residue window     fixed at construction. Not adaptively sized.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import numpy as np

from ..core import CoreConfig, ResidualCore
from .coupling import CoupledPacket, CouplingField


DEFAULT_F_RES = 0.1
DEFAULT_DELTA_S = 0.5
DEFAULT_MU = 0


def _hash_joint_bins(theta: np.ndarray, n_bins: int = 4) -> int:
    """Discretize (N,) phases into a unique integer joint-bin label.

    Each phase maps to a bin in [0, n_bins). The joint mode is the
    integer sum of bin_i * n_bins**i over i. This is a coarse mode
    label, useful for `basin.py` tests (RES-318 §8 invariant 5).
    """
    if n_bins < 2:
        raise ValueError("n_bins must be >= 2")
    mode = 0
    for i, p in enumerate(theta):
        b = int(((float(p) + np.pi) / (2.0 * np.pi)) * n_bins) % n_bins
        mode += b * (n_bins ** i)
    return mode


class EngineGroup:
    """N residual cores + one coupling field.

    Construction:
        configs = [CoreConfig(m=8, n=8, r=4) for _ in range(3)]
        field = CouplingField(n_engines=3, kappa=2.0, seed=0)
        group = EngineGroup(configs, field, seed=0)

        W_per_engine = [rng.standard_normal((8, 8)) for _ in range(3)]
        drives = np.array([0.1, -0.1, 0.05])
        coupled = group.step(W_per_engine, drives=drives)
        coupled.R_shared, coupled.coupling_matrix
    """

    def __init__(
        self,
        core_configs: list[CoreConfig],
        coupling: CouplingField,
        beta_F: float = 0.1,
        beta_S: float = 0.1,
        residue_window: int = 8,
        version: str = "1.0.0",
        seed: int = 0,
    ) -> None:
        if len(core_configs) < 1:
            raise ValueError("core_configs must be non-empty")
        if coupling.n_engines != len(core_configs):
            raise ValueError(
                f"coupling.n_engines={coupling.n_engines} != "
                f"len(core_configs)={len(core_configs)}"
            )
        if residue_window < 1:
            raise ValueError("residue_window must be >= 1")

        self.core_configs = list(core_configs)
        self.coupling = coupling
        self.beta_F = float(beta_F)
        self.beta_S = float(beta_S)
        self.residue_window = int(residue_window)
        self.version = str(version)
        self.seed = int(seed)
        self.n_engines = len(core_configs)

        self.cores = [
            ResidualCore(
                cfg,
                seed=self.seed + i,
                non_conservative=True,
            )
            for i, cfg in enumerate(self.core_configs)
        ]

        # Own-monitor state, initialized to fixed defaults
        self._F_res_own = np.full(self.n_engines, DEFAULT_F_RES)
        self._DeltaS_own = np.full(self.n_engines, DEFAULT_DELTA_S)
        self._mu_own = np.full(self.n_engines, DEFAULT_MU, dtype=int)

        # Per-engine residue history (empty at construction)
        self._residue: list[list[float]] = [[] for _ in range(self.n_engines)]

        self._step_count = 0

    # ── cross terms (RES-318 §5) ────────────────────────────────────
    def _apply_cross(
        self,
        i: int,
        own: dict,
        phase_diff: np.ndarray,
    ) -> dict:
        N = self.n_engines
        if N == 1:
            return dict(own)

        diffs = np.abs(phase_diff[i].copy())
        diffs[i] = -1.0
        j_bar = int(np.argmax(diffs))
        d_bar = float(phase_diff[i, j_bar])

        sum_abs = float(
            sum(abs(phase_diff[i, j]) for j in range(N) if j != i)
        )
        F_res_cross = self.beta_F * sum_abs / (N - 1)
        F_res_i = float(own["F_res"]) + F_res_cross

        DeltaS_cross = self.beta_S * (1.0 - np.cos(d_bar))
        DeltaS_i = float(own["DeltaS"]) + float(DeltaS_cross)

        mu_i = int(own["mu"]) ^ int(d_bar < 0.0)

        return {"F_res": F_res_i, "DeltaS": DeltaS_i, "mu": mu_i}

    # ── step ────────────────────────────────────────────────────────
    def step(
        self,
        W_per_engine: list[np.ndarray],
        monitors_own: Optional[list[dict]] = None,
        drives: Optional[np.ndarray] = None,
    ) -> CoupledPacket:
        """Advance all N cores and the coupling field one step.

        W_per_engine : list of (m_i, n_i) matrices, one per engine
        monitors_own : optional list of {'F_res', 'DeltaS', 'mu'} dicts,
                       one per engine. If None, uses previous step's
                       own values (or defaults on step 1).
        drives       : optional (N,) drive per engine to the coupling
                       field.

        Returns a CoupledPacket holding N ControlPacket results plus
        the field state at emission time.
        """
        if len(W_per_engine) != self.n_engines:
            raise ValueError(
                f"W_per_engine length {len(W_per_engine)} != "
                f"n_engines {self.n_engines}"
            )

        # 1. Field step (external drive)
        self.coupling.step(drives=drives)

        # 2. Own monitors
        if monitors_own is None:
            own = [
                {
                    "F_res": float(self._F_res_own[i]),
                    "DeltaS": float(self._DeltaS_own[i]),
                    "mu": int(self._mu_own[i]),
                }
                for i in range(self.n_engines)
            ]
        else:
            if len(monitors_own) != self.n_engines:
                raise ValueError(
                    f"monitors_own length {len(monitors_own)} != "
                    f"n_engines {self.n_engines}"
                )
            own = monitors_own

        # 3. Apply cross terms
        phase_diff = self.coupling.coupling_matrix()
        adjusted = [
            self._apply_cross(i, own[i], phase_diff)
            for i in range(self.n_engines)
        ]

        # 4. Step each core
        packets = []
        for i in range(self.n_engines):
            packet = self.cores[i].step(
                W_per_engine[i],
                version=self.version,
                mu=int(adjusted[i]["mu"]),
                F_res=float(adjusted[i]["F_res"]),
                DeltaS=float(adjusted[i]["DeltaS"]),
            )
            packets.append(packet)

            # Update residue history
            self._residue[i].append(float(packet.DeltaS))
            if len(self._residue[i]) > self.residue_window:
                self._residue[i].pop(0)

            # Update own-monitor state for next step
            self._F_res_own[i] = float(adjusted[i]["F_res"])
            self._DeltaS_own[i] = float(packet.DeltaS)
            self._mu_own[i] = int(packet.mu)

        self._step_count += 1

        # 5. Build CoupledPacket
        residue = tuple(
            np.array(self._residue[i], dtype=np.float64)
            for i in range(self.n_engines)
        )
        return CoupledPacket(
            packets=tuple(packets),
            phases=tuple(self.coupling.theta.tolist()),
            R_shared=self.coupling.order_parameter(),
            coupling_matrix=self.coupling.coupling_matrix(),
            residue_history=residue,
        )

    # ── lifecycle ───────────────────────────────────────────────────
    def reset(self) -> None:
        """Reset field, cores, monitor state, residue, step count."""
        self.coupling.reset()
        self.cores = [
            ResidualCore(
                cfg,
                seed=self.seed + i,
                non_conservative=True,
            )
            for i, cfg in enumerate(self.core_configs)
        ]
        self._F_res_own = np.full(self.n_engines, DEFAULT_F_RES)
        self._DeltaS_own = np.full(self.n_engines, DEFAULT_DELTA_S)
        self._mu_own = np.full(self.n_engines, DEFAULT_MU, dtype=int)
        self._residue = [[] for _ in range(self.n_engines)]
        self._step_count = 0

    def snapshot(self) -> dict:
        return {
            "n_engines": int(self.n_engines),
            "step_count": int(self._step_count),
            "beta_F": float(self.beta_F),
            "beta_S": float(self.beta_S),
            "residue_window": int(self.residue_window),
            "version": self.version,
            "seed": int(self.seed),
            "coupling": self.coupling.snapshot(),
            "F_res_own": self._F_res_own.tolist(),
            "DeltaS_own": self._DeltaS_own.tolist(),
            "mu_own": self._mu_own.tolist(),
            "residue_lengths": [len(r) for r in self._residue],
        }

    def __repr__(self) -> str:
        return (
            f"EngineGroup(n={self.n_engines}, beta_F={self.beta_F}, "
            f"beta_S={self.beta_S}, step={self._step_count})"
        )


# ── data generator ──────────────────────────────────────────────────────
@dataclass
class CoupledStreamGenerator:
    """Yield CoupledPackets from an EngineGroup driven by an external source.

    The drive_source is a callable (t: int) -> (N,) array. It is the
    only external input. Everything else comes from the group's own
    state.

    W_source, if supplied, is a callable (t: int) -> list of (m_i, n_i)
    matrices. If None, W matrices are generated from the group seed
    plus t.
    """
    group: EngineGroup
    drive_source: Callable[[int], np.ndarray]
    W_source: Optional[Callable[[int], list]] = None
    _t: int = 0

    def _default_W_source(self, t: int) -> list:
        rng = np.random.default_rng(self.group.seed + t * 7919)
        return [
            rng.standard_normal((cfg.m, cfg.n))
            for cfg in self.group.core_configs
        ]

    def __iter__(self) -> Iterator[CoupledPacket]:
        while True:
            drives = np.asarray(
                self.drive_source(self._t), dtype=np.float64
            ).reshape(-1)
            if drives.shape != (self.group.n_engines,):
                raise ValueError(
                    f"drive_source returned shape {drives.shape}, "
                    f"expected ({self.group.n_engines},)"
                )

            if self.W_source is None:
                W_list = self._default_W_source(self._t)
            else:
                W_list = self.W_source(self._t)

            packet = self.group.step(W_list, drives=drives)
            self._t += 1
            yield packet

    def reset(self) -> None:
        self._t = 0
        self.group.reset()

    def take(self, n: int) -> list[CoupledPacket]:
        """Convenience: return the first n packets as a list."""
        if n < 0:
            raise ValueError("n must be >= 0")
        out: list[CoupledPacket] = []
        for i, pkt in enumerate(iter(self)):
            if i >= n:
                break
            out.append(pkt)
        return out


__all__ = [
    "EngineGroup",
    "CoupledStreamGenerator",
    "_hash_joint_bins",
]
