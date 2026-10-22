"""Coupling field and coupled packet for EngineGroup composition (RES-318).

The single-engine substrate (RES-200) couples the r oscillators within
one residual core. `KuramotoField` handles that and its contract is
stable. At group level (RES-318), N residual cores produce N packet
streams, and their monitors are coupled through an N-engine phase
lattice. That lattice is `CouplingField`.

Two types:

    CouplingField  — (N,) phases, one per engine, stepped together.
    CoupledPacket  — N single-engine packets plus cross-engine state at
                     the moment they were emitted.

Both are self-contained. Neither imports `ResidualCore`, `KuramotoField`,
or the hierarchy encoder. The `EngineGroup` in `engine_group.py` uses
both, but they can be tested without it.

Design notes:
    - The field uses `omega_base` for all engines by default (uniform
      ladder). Cross-engine diversity comes from `drives`, not from
      different base frequencies. A `golden_powers` ladder is available
      if frequency diversity is wanted, but the default matches the
      intent: N engines at the same base frequency, driven differently.
    - `alpha` is reserved for cross-engine frustration. It is accepted
      and stored for signature stability but unused in v1. When the
      EngineGroup drive rule needs frustration, alpha becomes live.
    - Coupling weights `W` default to all-ones minus identity,
      matching `KuramotoField._W_osc`.

Off states (explicit):
    trainable              off. No parameters, no gradients.
    cross-engine residue   off. CoupledPacket stores residue history;
                           the field does not compute or propagate it.
    packet-format change   off. The N underlying packets are standard
                           HierarchicalPacket instances (RES-310).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from ..hierarchy.encoder import HierarchicalPacket


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

    The field does not know about residual cores, packets, or monitors.
    It holds N phases, steps them under a Kuramoto update with external
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
        """Initialize the coupling field.

        Parameters
        ----------
        n_engines : int
            Number of engines (>= 1). Fixed at construction.
        kappa : float
            Cross-engine coupling strength (>= 0). kappa=0 means no
            coupling; engines evolve independently.
        alpha : float
            Reserved for cross-engine frustration. Stored but unused in
            v1.
        dt : float
            Integration step (> 0).
        omega_base : float
            Base angular frequency. With ladder="uniform", all engines
            share this frequency.
        ladder : str
            "uniform" (default) or "golden_powers". With "golden_powers",
            omega_i = omega_base * PHI^(-i).
        random_start : bool
            If True, initial phases are uniform in (-pi, pi]. If False,
            all phases start at 0.
        seed : int
            RNG seed for the initial phase distribution.
        """
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

    # ── ladders ─────────────────────────────────────────────────────
    def _compute_omega(self) -> np.ndarray:
        if self.ladder == "uniform":
            return np.full(self.n_engines, self.omega_base, dtype=np.float64)
        powers = PHI ** (-np.arange(self.n_engines, dtype=np.float64))
        return self.omega_base * powers

    # ── state access ────────────────────────────────────────────────
    @property
    def theta(self) -> np.ndarray:
        """Current phase per engine. (N,) copy."""
        return self._theta.copy()

    @property
    def omega(self) -> np.ndarray:
        """Base frequency per engine. (N,) copy."""
        return self._omega.copy()

    # ── step ────────────────────────────────────────────────────────
    def step(
        self,
        drives: Optional[np.ndarray] = None,
        W: Optional[np.ndarray] = None,
    ) -> None:
        """Advance one step.

        Parameters
        ----------
        drives : (N,) array or None
            Per-engine external drive. Added to each engine's phase
            velocity. None is equivalent to zeros.
        W : (N, N) array or None
            Coupling weights. W[i,j] is the coupling from engine j to
            engine i. Diagonal is ignored (self-coupling). Default is
            all-ones minus identity.

        Update rule (standard Kuramoto with external forcing):

            dtheta_i = omega_i
                     + (kappa / N) * sum_j W[i,j] * sin(theta_j - theta_i)
                     + drives[i]
            theta_i += dt * dtheta_i
            theta_i wrapped to (-pi, pi]
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
        # Pairwise phase differences: sin(theta_j - theta_i)
        sin_diff = np.sin(theta[None, :] - theta[:, None])  # (N, N)
        coupling = (self.kappa / N) * np.sum(W_arr * sin_diff, axis=1)

        dtheta = self._omega + coupling + drives_arr
        new_theta = theta + self.dt * dtheta
        # Wrap to (-pi, pi]
        self._theta = np.mod(new_theta + np.pi, TWO_PI) - np.pi

    # ── observables ─────────────────────────────────────────────────
    def order_parameter(self) -> float:
        """Kuramoto order parameter over the N engine phases. In [0, 1]."""
        z = np.exp(1j * self._theta)
        return float(np.abs(np.mean(z)))

    def phase_difference(self, i: int, j: int) -> float:
        """Signed phase difference theta_i - theta_j, wrapped to (-pi, pi]."""
        if not (0 <= i < self.n_engines):
            raise IndexError(f"i={i} out of range [0, {self.n_engines})")
        if not (0 <= j < self.n_engines):
            raise IndexError(f"j={j} out of range [0, {self.n_engines})")
        d = self._theta[i] - self._theta[j]
        return float(np.mod(d + np.pi, TWO_PI) - np.pi)

    def coupling_matrix(self) -> np.ndarray:
        """(N, N) antisymmetric matrix of wrapped phase differences.

        coupling_matrix()[i, j] == phase_difference(i, j).
        Diagonal is zero.
        """
        raw = self._theta[:, None] - self._theta[None, :]  # (N, N)
        return np.mod(raw + np.pi, TWO_PI) - np.pi

    # ── lifecycle ───────────────────────────────────────────────────
    def reset(self) -> None:
        """Restore initial phases using the same seed."""
        self._rng = np.random.default_rng(self.seed)
        if self.random_start:
            self._theta = self._rng.uniform(-np.pi, np.pi, self.n_engines)
        else:
            self._theta = np.zeros(self.n_engines, dtype=np.float64)

    def snapshot(self) -> dict:
        """JSON-serializable state."""
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

    Fields
    ------
    packets : tuple[HierarchicalPacket, ...]
        One packet per engine. Length N. Emitted together in one step.
    phases : tuple[float, ...]
        Phase per engine at emission time. Length N.
    R_shared : float
        CouplingField.order_parameter() at emission time. In [0, 1].
    coupling_matrix : np.ndarray
        (N, N) antisymmetric matrix of wrapped phase differences at
        emission time. Diagonal zero.
    residue_history : tuple[np.ndarray, ...]
        Per-engine ΔS history. Each is (K,) with K the history length.
        Length N.
    """
    packets: tuple
    phases: tuple
    R_shared: float
    coupling_matrix: np.ndarray
    residue_history: tuple

    def __post_init__(self) -> None:
        # Coerce to tuple (in case caller passed a list)
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
            raise ValueError(
                f"R_shared={R} must be in [0, 1]"
            )
        object.__setattr__(self, "R_shared", R)

        M = np.asarray(self.coupling_matrix, dtype=np.float64)
        if M.shape != (n, n):
            raise ValueError(
                f"coupling_matrix shape {M.shape} != ({n}, {n})"
            )
        if not np.allclose(np.diag(M), 0.0, atol=1e-9):
            raise ValueError("coupling_matrix diagonal must be zero")
        # Antisymmetry up to wrap boundary: |M| must equal |M.T|
        if not np.allclose(np.abs(M), np.abs(M.T), atol=1e-6):
            raise ValueError(
                "coupling_matrix must be antisymmetric "
                "(|M| == |M.T| within wrap tolerance)"
            )
        object.__setattr__(
            self, "coupling_matrix", M
        )

        for i, h in enumerate(self.residue_history):
            arr = np.asarray(h, dtype=np.float64)
            if arr.ndim != 1:
                raise ValueError(
                    f"residue_history[{i}] must be 1-D, got shape {arr.shape}"
                )
            object.__setattr__(
                self, "residue_history",
                self.residue_history[:i] + (arr,) + self.residue_history[i+1:]
            )

    # ── properties ──────────────────────────────────────────────────
    @property
    def n_engines(self) -> int:
        return len(self.packets)

    # ── serialization ───────────────────────────────────────────────
    def to_dict(self) -> dict:
        """JSON-serializable summary. Packet hv is reduced to its dim."""
        return {
            "n_engines": self.n_engines,
            "packets": [
                {
                    "level": int(p.level),
                    "span_start": int(p.span_start),
                    "span_end": int(p.span_end),
                    "child_count": int(p.child_count),
                    "hv_dim": int(p.hv.shape[0]) if p.hv is not None else 0,
                }
                for p in self.packets
            ],
            "phases": [float(x) for x in self.phases],
            "R_shared": float(self.R_shared),
            "coupling_matrix": self.coupling_matrix.tolist(),
            "residue_history": [
                h.tolist() for h in self.residue_history
            ],
        }


__all__ = ["CouplingField", "CoupledPacket", "PHI", "TWO_PI"]
