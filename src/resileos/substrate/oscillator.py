"""
Kuramoto-coupled phase dynamics for the non-conservative operator.

The operator's theta field evolves in one of two ways:

    linear (default)   theta += (2*mu - 1) * phase_max * pattern
                       No intrinsic frequencies, no coupling. This is
                       what RES-200 §extension currently implements.

    oscillator         dtheta_i/dt = omega_i
                                    + kappa / (alpha + epsilon)
                                      * sum_j W_ij sin(theta_j - theta_i)
                       with omega_i from a golden-ratio ladder and W_ij
                       from an optional coupling matrix (typically the
                       adjacency of a PhasorGraph).

The oscillator field is a classical dynamical system. It runs on CPU.
No quantum capability is claimed or required.

Design continuity with QD-TER-Human-Medium:
    - coupling form matches EEG_hyperscan.py::_coupled_oscillator
    - v5.0 §3 global chiral commutator has the same sin(delta) form
    - golden-ratio spacing is the structural signature from
      QD-TER_HumanMedium_v7.0_PartII.md §1.2.1

The coupling sign is Option A from the design notes:

    kappa / (alpha + epsilon)

High coupling at low error, convergence; low coupling at high error,
descent to quasi-periodic drift. This matches the substrate's existing
behavior (Titanos converges when confident, explores when uncertain).
"""
from __future__ import annotations

import math

import numpy as np

from ..state_dtype import state_dtype

PHI = (1.0 + np.sqrt(5.0)) / 2.0


# ── frequency ladders ───────────────────────────────────────────────────
def golden_ladder(r: int, omega_base: float = 2.0 * np.pi) -> np.ndarray:
    """
    omega_i = phi^i mod omega_base.

    Powers of phi are maximally irrational. The ladder reduces the
    density of near-resonances and delays the onset of partial locking.
    It does not eliminate resonance; for any eps > 0 there exist indices
    i, j with |omega_i / omega_j - p/q| < eps. The events are rare and
    slow, not impossible.
    """
    powers = PHI ** np.arange(r, dtype=state_dtype())
    return np.mod(powers, omega_base)


def golden_weyl(r: int, omega_base: float = 2.0 * np.pi) -> np.ndarray:
    """
    omega_i = omega_base * frac(phi * i).

    Alternative ladder. More uniform coverage of [0, omega_base) than
    the powers. Also incommensurate in the sense that no pair forms a
    rational ratio exactly.
    """
    i = np.arange(r, dtype=state_dtype())
    frac = np.mod(PHI * i, 1.0)
    return frac * omega_base


_LADDERS = {
    "golden_powers": golden_ladder,
    "golden_weyl": golden_weyl,
}


# ── coupling helpers ────────────────────────────────────────────────────
def coupling_from_graph(graph) -> np.ndarray:
    """
    Symmetric non-negative coupling from a PhasorGraph.

    W_ij = |A_ij|, diagonal zero. For a Hermitian graph, |A_ij| = |A_ji|,
    so the coupling is symmetric. The amplitudes carry the topology; the
    phases of the complex weights are not used here.
    """
    A = np.asarray(graph.adjacency(), dtype=np.complex128)
    W = np.abs(A)
    np.fill_diagonal(W, 0.0)
    return W


def empty_coupling(r: int) -> np.ndarray:
    return np.zeros((r, r), dtype=state_dtype())


# ── Kuramoto field ──────────────────────────────────────────────────────
class KuramotoField:
    """
    Phase dynamics for r coupled oscillators.

        dtheta_i/dt = omega_i
                    + kappa / (alpha + epsilon)
                      * sum_j W_ij sin(theta_j - theta_i)

    Parameters
    ----------
    r : int
        Number of oscillators. Matches the scar rank.
    ladder : str
        'golden_powers' (phi^i mod omega_base) or
        'golden_weyl'   (omega_base * frac(phi * i)).
    omega_base : float
        Upper bound for the frequency range.
    kappa : float
        Base coupling strength.
    alpha : float
        Regularizer in the denominator (prevents division by zero at
        epsilon = 0).
    dt : float
        Integration step. RK4 by default.
    seed : int
        Used only if random_start is True.
    random_start : bool
        If True, initialize theta uniform in [-pi, pi]. Otherwise zero.
    """

    def __init__(
        self,
        r: int,
        ladder: str = "golden_powers",
        omega_base: float = 2.0 * np.pi,
        kappa: float = 1.0,
        alpha: float = 1e-3,
        dt: float = 0.1,
        seed: int = 0,
        random_start: bool = False,
    ) -> None:
        if r < 1:
            raise ValueError("r must be >= 1")
        if ladder not in _LADDERS:
            raise ValueError(f"unknown ladder {ladder!r}")
        if alpha <= 0.0:
            raise ValueError("alpha must be > 0")
        if dt <= 0.0:
            raise ValueError("dt must be > 0")

        self.r = int(r)
        self.ladder = ladder
        self.omega_base = float(omega_base)
        self.kappa = float(kappa)
        self.alpha = float(alpha)
        self.dt = float(dt)
        self.omega = _LADDERS[ladder](self.r, self.omega_base)

        if random_start:
            rng = np.random.default_rng(seed)
            self.theta = rng.uniform(-np.pi, np.pi, size=self.r)
        else:
            self.theta = np.zeros(self.r, dtype=state_dtype())

        self._last_epsilon = 0.0

    # ── dynamics ────────────────────────────────────────────────────
    def _dtheta(self, theta: np.ndarray, epsilon: float,
                W: np.ndarray) -> np.ndarray:
        # diff[i, j] = theta[j] - theta[i]
        diff = theta[None, :] - theta[:, None]
        coupling = (W * np.sin(diff)).sum(axis=1)
        gain = self.kappa / (self.alpha + float(epsilon))
        return self.omega + gain * coupling

    def velocity(self, theta: np.ndarray | None = None,
                 epsilon: float = 0.0,
                 W: np.ndarray | None = None) -> np.ndarray:
        """
        Public wrapper for the phase velocity dtheta/dt.

        If theta is None, uses the current field state. If W is None,
        no coupling (each oscillator rotates at its own omega_i).

        This is the same vector the RK4 integrator uses internally.
        Callers that need the instantaneous phase velocity — e.g. a
        search that biases proposals by the sign of dtheta — should
        call this method rather than reaching into _dtheta.
        """
        if theta is None:
            theta = self.theta
        theta = np.asarray(theta, dtype=state_dtype())
        if theta.shape != (self.r,):
            raise ValueError(
                f"theta shape {theta.shape} != ({self.r},)")
        if W is None:
            W = empty_coupling(self.r)
        W = np.asarray(W, dtype=state_dtype())
        if W.shape != (self.r, self.r):
            raise ValueError(
                f"W shape {W.shape} != ({self.r}, {self.r})")
        return self._dtheta(theta, epsilon, W)

    def step(self, epsilon: float, W: np.ndarray | None = None,
             dt: float | None = None) -> np.ndarray:
        """
        Advance the field by one RK4 step. Returns the new theta.

        epsilon is the tracking error; small epsilon means strong
        coupling (Option A). W is the (r, r) coupling matrix; if None,
        no coupling (each oscillator rotates at its own omega_i).
        """
        dt = self.dt if dt is None else float(dt)
        if dt <= 0.0:
            raise ValueError("dt must be > 0")
        if W is None:
            W = empty_coupling(self.r)
        W = np.asarray(W)
        if W.shape != (self.r, self.r):
            raise ValueError(
                f"W shape {W.shape} != ({self.r}, {self.r})")

        # One RK4 step of the documented ODE is exact when W is zero.
        # Under strong coupling the same dt moves phases by many radians
        # and the field does not lock. Subdivide only that case.
        gain = abs(self.kappa / (self.alpha + float(epsilon)))
        row = float(np.max(np.sum(np.abs(W), axis=1))) if self.r else 0.0
        max_phase = 0.2
        nsub = 1
        if gain * row * dt > max_phase:
            nsub = int(math.ceil((gain * row * dt) / max_phase))
            nsub = max(1, min(nsub, 20000))

        def _rk4(theta: np.ndarray, h: float, coupling: np.ndarray) -> np.ndarray:
            k1 = self._dtheta(theta, epsilon, coupling)
            k2 = self._dtheta(theta + 0.5 * h * k1, epsilon, coupling)
            k3 = self._dtheta(theta + 0.5 * h * k2, epsilon, coupling)
            k4 = self._dtheta(theta + h * k3, epsilon, coupling)
            return theta + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        def _wrap(theta: np.ndarray) -> np.ndarray:
            return ((theta + np.pi) % (2.0 * np.pi)) - np.pi

        if nsub == 1:
            theta = _wrap(_rk4(self.theta, dt, np.asarray(W, dtype=state_dtype())))
            self.theta = np.asarray(theta, dtype=state_dtype())
        else:
            theta = np.asarray(self.theta, dtype=np.float64)
            coupling = np.asarray(W, dtype=np.float64)
            h = dt / nsub
            for _ in range(nsub):
                theta = _wrap(_rk4(theta, h, coupling))
            self.theta = np.asarray(theta, dtype=state_dtype())
        self._last_epsilon = float(epsilon)
        return self.theta.copy()

    # ── readouts ────────────────────────────────────────────────────
    def order_parameter(self) -> float:
        """
        R = (1/r) |sum_j exp(i * theta_j)|.

        R = 1 when all phases equal; R -> 0 when uniformly distributed.
        """
        z = np.exp(1j * self.theta)
        return float(np.abs(np.mean(z)))

    def mean_phase(self) -> float:
        z = np.exp(1j * self.theta)
        return float(np.angle(np.mean(z)))

    def reset(self) -> None:
        self.theta[:] = 0.0

    # ── persistence ─────────────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "r": self.r,
            "ladder": self.ladder,
            "omega_base": self.omega_base,
            "kappa": self.kappa,
            "alpha": self.alpha,
            "dt": self.dt,
            "omega": self.omega.tolist(),
            "theta": self.theta.tolist(),
        }

    def load_state_dict(self, d: dict) -> None:
        if d["r"] != self.r:
            raise ValueError(f"r mismatch: {d['r']} vs {self.r}")
        self.omega = np.asarray(d["omega"], dtype=state_dtype())
        self.theta = np.asarray(d["theta"], dtype=state_dtype())
        self.kappa = float(d.get("kappa", self.kappa))
        self.alpha = float(d.get("alpha", self.alpha))
        self.dt = float(d.get("dt", self.dt))


__all__ = [
    "KuramotoField",
    "golden_ladder",
    "golden_weyl",
    "coupling_from_graph",
    "empty_coupling",
    "PHI",
]
