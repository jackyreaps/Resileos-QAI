"""Coupling field and coupled packet for EngineGroup composition (RES-318).

The single-engine substrate (RES-200) couples the r oscillators within one
residual core. `KuramotoField` handles that and its contract is stable. At
group level (RES-318), N residual cores produce N packet streams, and their
monitors are coupled through an N-engine phase lattice. That lattice is
`CouplingField`.

Two types:

    CouplingField — (N,) phases, one per engine, stepped together.
    CoupledPacket — N single-engine packets plus cross-engine state at the
                    moment they were emitted.

Both are self-contained. Neither imports `ResidualCore`, `KuramotoField`, or
the hierarchy encoder. The `EngineGroup` in `engine_group.py` uses both, but
they can be tested without it.

CoupledPacket is packet-type agnostic: it holds whatever the engines emit.
`ResidualCore.step()` returns a `ControlPacket`; the hierarchy encoder emits
`HierarchicalPacket`. `to_dict()` inspects the packet and serializes what it
can.

Off states (explicit):
    trainable off. No parameters, no gradients.
    cross-engine residue off. CoupledPacket stores residue history; the field
        does not compute or propagate it.
    packet-format change off. The N underlying packets are whatever each
        engine emits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

PHI = (1.0 + np.sqrt(5.0)) / 2.0
TWO_PI = 2.0 * np.pi


# ── coupling field ──────────────────────────────────────────────────────


class CouplingField:
    """N-engine phase lattice. One phase per engine.

    Construction:

        field = CouplingField(n_engines=3, kappa=1.0, seed=0)
        field.step(drives=np.array([0.1, -0.2, 0.3]))
        R = field.order_parameter()
        d = field.phase_difference(0, 1)

    The field does not know about residual cores, packets, or monitors. It
    holds N phases, steps them under a Kuramoto update with external
    per-engine drive, and exposes the order parameter and pairwise phase
    differences.
    """

    def __init__(
        self,
        n_engines: int,
        kappa: float = 1.0,
        alpha: float = 0.5,
        dt: float = 0.1,
        omega_base: float = TWO_PI,
        ladder: str = "uniform",
        random_start: bool = True,
        seed: int = 0,
    ) -> None:
        if n_engines < 1:
            raise ValueError("n_engines must be >= 1")
        if kappa < 0.0:
            raise ValueError("kappa must be >= 0")
        if dt <= 0.0:
            raise ValueError("dt must be > 0")
        if ladder not in ("uniform", "golden_powers"):
            raise ValueError(f"unknown ladder: {ladder!r}")
        self.n_engines = int(n_engines)
        self.kappa = float(kappa)
        self.alpha = float(alpha)  # reserved
        self.dt = float(dt)
        self.omega_base = float(omega_base)
        self.ladder = ladder
        self.random_start = bool(random_start)
        self.seed = int(seed)
        self._rng = np.random.default_rng(self.seed)
        if self.random_start:
            self._theta = self._rng.uniform(-np.pi, np.pi, self.n_engines)
        else:
            self._theta = np.zeros(self.n_engines, dtype=np.float64)
        self._omega = self._compute_omega()

    def _compute_omega(self) -> np.ndarray:
        if self.ladder == "uniform":
            return np.full(self.n_engines, self.omega_base, dtype=np.float64)
        powers = PHI ** (-np.arange(self.n_engines, dtype=np.float64))
        return self.omega_base * powers

    @property
    def theta(self) -> np.ndarray:
        return self._theta.copy()

    @property
    def omega(self) -> np.ndarray:
        return self._omega.copy()

    def step(
        self,
        drives: Optional[np.ndarray] = None,
        W: Optional[np.ndarray] = None,
    ) -> None:
        """Advance one step.

            dtheta_i = omega_i
                     + (kappa / N) * sum_j W[i,j] * sin(theta_j - theta_i)
                     + drives[i]
            theta_i += dt * dtheta_i   (wrapped to (-pi, pi])
        """
        N = self.n_engines
        if drives is None:
            drives_arr = np.zeros(N, dtype=np.float64)
        else:
            drives_arr = np.asarray(drives, dtype=np.float64).reshape(-1)
            if drives_arr.shape != (N,):
                raise ValueError(
                    f"drives shape {drives_arr.shape} != ({N},)"
                )
        if W is None:
            W_arr = np.ones((N, N), dtype=np.float64) - np.eye(N)
        else:
            W_arr = np.asarray(W, dtype=np.float64)
            if W_arr.shape != (N, N):
                raise ValueError(
                    f"W shape {W_arr.shape} != ({N}, {N})"
                )
        theta = self._theta
        sin_diff = np.sin(theta[None, :] - theta[:, None])
        coupling = (self.kappa / N) * np.sum(W_arr * sin_diff, axis=1)
        dtheta = self._omega + coupling + drives_arr
        new_theta = theta + self.dt * dtheta
        self._theta = np.mod(new_theta + np.pi, TWO_PI) - np.pi

    def order_parameter(self) -> float:
        z = np.exp(1j * self._theta)
        return float(np.abs(np.mean(z)))

    def phase_difference(self, i: int, j: int) -> float:
        if not (0 <= i < self.n_engines):
            raise IndexError(f"i={i} out of range [0, {self.n_engines})")
        if not (0 <= j < self.n_engines):
            raise IndexError(f"j={j} out of range [0, {self.n_engines})")
        d = self._theta[i] - self._theta[j]
        return float(np.mod(d + np.pi, TWO_PI) - np.pi)

    def coupling_matrix(self) -> np.ndarray:
        raw = self._theta[:, None] - self._theta[None, :]
        return np.mod(raw + np.pi, TWO_PI) - np.pi

    def reset(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        if self.random_start:
            self._theta = self._rng.uniform(-np.pi, np.pi, self.n_engines)
        else:
            self._theta = np.zeros(self.n_engines, dtype=np.float64)

    def snapshot(self) -> dict:
        return {
            "n_engines": int(self.n_engines),
            "kappa": float(self.kappa),
            "alpha": float(self.alpha),
            "dt": float(self.dt),
            "omega_base": float(self.omega_base),
            "ladder": self.ladder,
            "random_start": bool(self.random_start),
            "seed": int(self.seed),
            "theta": self._theta.tolist(),
            "omega": self._omega.tolist(),
            "R": self.order_parameter(),
        }

    def __repr__(self) -> str:
        return (
            f"CouplingField(n={self.n_engines}, kappa={self.kappa}, "
            f"dt={self.dt}, ladder={self.ladder!r})"
        )


# ── coupled packet ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CoupledPacket:
    """N single-engine packets plus cross-engine state at emission time.

    packets — tuple of whatever each engine emitted (ControlPacket from
        ResidualCore, HierarchicalPacket from the encoder, or any object).
    phases — (N,) phase per engine at emission time.
    R_shared — coupling order parameter at emission time, [0, 1].
    coupling_matrix — (N, N) antisymmetric wrapped phase differences.
    residue_history — (N,) tuple of (K,) ΔS histories.
    """
    packets: tuple
    phases: tuple
    R_shared: float
    coupling_matrix: np.ndarray
    residue_history: tuple

    def __post_init__(self) -> None:
        if not isinstance(self.packets, tuple):
            object.__setattr__(self, "packets", tuple(self.packets))
        if not isinstance(self.phases, tuple):
            object.__setattr__(self, "phases", tuple(self.phases))
        if not isinstance(self.residue_history, tuple):
            object.__setattr__(
                self, "residue_history", tuple(self.residue_history)
            )

        n = len(self.packets)
        if n < 1:
            raise ValueError("packets must contain at least one engine")
        if len(self.phases) != n:
            raise ValueError(
                f"len(phases)={len(self.phases)} != len(packets)={n}"
            )
        if len(self.residue_history) != n:
            raise ValueError(
                f"len(residue_history)={len(self.residue_history)} != {n}"
            )

        R = float(self.R_shared)
        if not (0.0 <= R <= 1.0 + 1e-9):
            raise ValueError(f"R_shared={R} must be in [0, 1]")
        object.__setattr__(self, "R_shared", R)

        M = np.asarray(self.coupling_matrix, dtype=np.float64)
        if M.shape != (n, n):
            raise ValueError(
                f"coupling_matrix shape {M.shape} != ({n}, {n})"
            )
        if not np.allclose(np.diag(M), 0.0, atol=1e-9):
            raise ValueError("coupling_matrix diagonal must be zero")
        if not np.allclose(M, -M.T, atol=1e-6):
            raise ValueError(
                "coupling_matrix must be antisymmetric "
                "(M == -M.T within tolerance)"
            )
        object.__setattr__(self, "coupling_matrix", M)

        for i, h in enumerate(self.residue_history):
            arr = np.asarray(h, dtype=np.float64)
            if arr.ndim != 1:
                raise ValueError(
                    f"residue_history[{i}] must be 1-D, got shape {arr.shape}"
                )
            object.__setattr__(
                self,
                "residue_history",
                self.residue_history[:i] + (arr,) + self.residue_history[i + 1:],
            )

    @property
    def n_engines(self) -> int:
        return len(self.packets)

    def to_dict(self) -> dict:
        """JSON-serializable summary. Handles any packet type."""
        packets_info = []
        for p in self.packets:
            if hasattr(p, "hv") and hasattr(p, "level"):
                packets_info.append({
                    "kind": "hierarchical",
                    "level": int(p.level),
                    "span_start": int(p.span_start),
                    "span_end": int(p.span_end),
                    "child_count": int(p.child_count),
                    "hv_dim": int(p.hv.shape[0]) if p.hv is not None else 0,
                })
            elif hasattr(p, "lat_s_k"):
                packets_info.append({
                    "kind": "control",
                    "rank": int(p.rank) if hasattr(p, "rank") else None,
                    "mu": int(p.mu) if hasattr(p, "mu") else None,
                    "DeltaS": float(p.DeltaS) if hasattr(p, "DeltaS") else None,
                    "volume_ok": (
                        bool(p.volume_ok) if hasattr(p, "volume_ok") else None
                    ),
                    "packet_hash": (
                        str(p.packet_hash)[:12]
                        if hasattr(p, "packet_hash") else None
                    ),
                })
            else:
                packets_info.append({
                    "kind": "unknown",
                    "repr": repr(p)[:80],
                })
        return {
            "n_engines": self.n_engines,
            "packets": packets_info,
            "phases": [float(x) for x in self.phases],
            "R_shared": float(self.R_shared),
            "coupling_matrix": self.coupling_matrix.tolist(),
            "residue_history": [h.tolist() for h in self.residue_history],
        }


__all__ = ["CouplingField", "CoupledPacket", "PHI", "TWO_PI"]
