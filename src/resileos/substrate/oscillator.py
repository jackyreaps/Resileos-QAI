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

Depth. The field is not one phase ring. It has `depth` levels (default
2), the same outward stack the hierarchy already uses: level 0 is the
inner vector, and each next level sits at the φ-power address
`ω · φ^{-level}` (RES-323). Inside a level the ODE above is unchanged.
Between levels the same sine coupling runs outward only — level L-1
drives level L with weight φ^{-1}, and the outer level does not drive
back. `theta` and the order parameter stay the inner vector of length
`r` (RES-316). A flat ring (`depth < 2`), fewer than two oscillators,
or a phase vector whose shape is not `(r,)` is rejected. A reversed
orientation is rejected. Those are the configurations that measure
order on too few vectors, or on the wrong axis, and then look like the
coupling failed.

The RK4 subdivision under a stiff within-level step is a numerical
safety. It is not what orders the field. The sine coupling on this
stack is.
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
        If True, initialize every level uniform in [-pi, pi], level 0
        first so an existing seed still reproduces the inner vector.
        Otherwise zero.
    depth : int
        Number of levels. Level 0 is inner. Must be >= 2. A depth of 1
        is the flat ring and is rejected.
    orientation : str
        Only ``outward`` is accepted: level L-1 drives level L. Any
        other axis is rejected rather than silently reversed.
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
        depth: int = 2,
        orientation: str = "outward",
    ) -> None:
        if r < 2:
            raise ValueError(
                "r must be >= 2; fewer than two oscillators is too few "
                "vectors to couple"
            )
        if isinstance(depth, bool) or isinstance(depth, float):
            raise ValueError("depth must be an int >= 2")
        if int(depth) < 2:
            raise ValueError(
                "depth must be >= 2; a single ring has no outward level"
            )
        if orientation != "outward":
            raise ValueError(
                "orientation must be 'outward' (inner level drives the "
                f"next); got {orientation!r}"
            )
        if ladder not in _LADDERS:
            raise ValueError(f"unknown ladder {ladder!r}")
        if alpha <= 0.0:
            raise ValueError("alpha must be > 0")
        if dt <= 0.0:
            raise ValueError("dt must be > 0")

        self.r = int(r)
        self.depth = int(depth)
        self.orientation = orientation
        self.ladder = ladder
        self.omega_base = float(omega_base)
        self.kappa = float(kappa)
        self.alpha = float(alpha)
        self.dt = float(dt)
        self.omega = _LADDERS[ladder](self.r, self.omega_base)
        self._levels = np.zeros((self.depth, self.r), dtype=state_dtype())

        if random_start:
            rng = np.random.default_rng(seed)
            # Level 0 first: the same draw the flat field used for `theta`.
            self._levels[0] = rng.uniform(-np.pi, np.pi, size=self.r)
            if self.depth > 1:
                self._levels[1:] = rng.uniform(
                    -np.pi, np.pi, size=(self.depth - 1, self.r)
                )

        self._last_epsilon = 0.0

    # ── phases ──────────────────────────────────────────────────────
    @property
    def theta(self) -> np.ndarray:
        """Inner phase vector, shape `(r,)`. This is the RES-316 field."""
        return self._levels[0]

    @theta.setter
    def theta(self, value: np.ndarray) -> None:
        arr = np.asarray(value, dtype=state_dtype())
        if arr.shape != (self.r,):
            raise ValueError(
                f"phase vector shape {arr.shape} != ({self.r},); "
                "too few or mis-oriented vectors"
            )
        self._levels[0] = arr

    def _check_level(self, level: int) -> None:
        if not (0 <= int(level) < self.depth):
            raise ValueError(
                f"level {level} out of range [0, {self.depth})"
            )

    def level_phases(self, level: int) -> np.ndarray:
        """Copy of the phase vector at `level`. Axis 0 of the stack is level."""
        self._check_level(level)
        return self._levels[int(level)].copy()

    def set_level_phases(self, level: int, theta: np.ndarray) -> None:
        self._check_level(level)
        arr = np.asarray(theta, dtype=state_dtype())
        if arr.shape != (self.r,):
            raise ValueError(
                f"phase vector shape {arr.shape} != ({self.r},); "
                "too few or mis-oriented vectors"
            )
        self._levels[int(level)] = arr

    def set_levels(self, levels: np.ndarray) -> None:
        """
        Replace the stack. Shape must be `(depth, r)`, level 0 inward.

        A stack stored as `(r, depth)` is the wrong axis and is rejected
        when the two sizes differ. A 1-d vector is too few levels.
        """
        arr = np.asarray(levels, dtype=state_dtype())
        if arr.ndim == 1:
            raise ValueError(
                f"levels shape {arr.shape} has no depth axis; "
                f"expected ({self.depth}, {self.r})"
            )
        if (
            arr.shape == (self.r, self.depth)
            and self.r != self.depth
        ):
            raise ValueError(
                f"levels shape {arr.shape} is oriented on the wrong axis; "
                f"expected ({self.depth}, {self.r}) with level 0 inward"
            )
        if arr.shape != (self.depth, self.r):
            raise ValueError(
                f"levels shape {arr.shape} != ({self.depth}, {self.r})"
            )
        self._levels[:] = arr

    def level_order(self, level: int) -> float:
        """Kuramoto R at one level. Same formula as `order_parameter`."""
        self._check_level(level)
        z = np.exp(1j * np.asarray(self._levels[int(level)], dtype=np.float64))
        return float(np.abs(np.mean(z)))

    def depth_order(self) -> float:
        """Mean of the per-level order parameters. Each term is RES-316 R."""
        return float(np.mean([self.level_order(i) for i in range(self.depth)]))

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
        # Under strong within-level coupling the same dt can move phases
        # by many radians. Subdividing that case is a numerical safety.
        # It is not the ordering mechanism: ordering is the sine coupling,
        # inside a level and outward from level L-1 to level L.
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
        self._advance_outer_levels(float(epsilon), W, dt, nsub)
        self._last_epsilon = float(epsilon)
        return self.theta.copy()

    def _advance_outer_levels(
        self,
        epsilon: float,
        W: np.ndarray,
        dt: float,
        nsub: int,
    ) -> None:
        """
        Drive levels 1..depth-1 from the level inside them.

        Within a level the derivative is the documented ODE, with
        `ω` scaled by `φ^{-level}` (the ingestion address of that level).
        The extra term is the same sine coupling, outward only:

            φ^{-1} * κ/(α+ε) * sin(θ_{level-1} - θ_level)

        Level 0 is not modified here. The inner phase is the value after
        this step's inner update, held while the outer level is integrated.
        """
        if self.depth < 2:
            return
        gain = self.kappa / (self.alpha + float(epsilon))
        outward_weight = float(PHI ** -1)
        h = float(dt) / int(nsub)
        levels = np.asarray(self._levels, dtype=np.float64)
        coupling = np.asarray(W, dtype=np.float64)
        omega0 = np.asarray(self.omega, dtype=np.float64)

        def deriv(phases: np.ndarray, level: int, inner: np.ndarray) -> np.ndarray:
            diff = phases[None, :] - phases[:, None]
            within = (coupling * np.sin(diff)).sum(axis=1)
            omega = omega0 * (PHI ** (-int(level)))
            pull = outward_weight * np.sin(inner - phases)
            return omega + gain * within + gain * pull

        def rk4(phases: np.ndarray, level: int, inner: np.ndarray) -> np.ndarray:
            k1 = deriv(phases, level, inner)
            k2 = deriv(phases + 0.5 * h * k1, level, inner)
            k3 = deriv(phases + 0.5 * h * k2, level, inner)
            k4 = deriv(phases + h * k3, level, inner)
            return phases + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        def wrap(phases: np.ndarray) -> np.ndarray:
            return ((phases + np.pi) % (2.0 * np.pi)) - np.pi

        for level in range(1, self.depth):
            phases = levels[level].copy()
            inner = levels[level - 1]
            for _ in range(int(nsub)):
                phases = wrap(rk4(phases, level, inner))
            levels[level] = phases
        self._levels[1:] = np.asarray(levels[1:], dtype=state_dtype())

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
        self._levels[...] = 0

    # ── persistence ─────────────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "r": self.r,
            "depth": self.depth,
            "orientation": self.orientation,
            "ladder": self.ladder,
            "omega_base": self.omega_base,
            "kappa": self.kappa,
            "alpha": self.alpha,
            "dt": self.dt,
            "omega": self.omega.tolist(),
            "theta": self.theta.tolist(),
            "levels": self._levels.tolist(),
        }

    def load_state_dict(self, d: dict) -> None:
        if d["r"] != self.r:
            raise ValueError(f"r mismatch: {d['r']} vs {self.r}")
        self.omega = np.asarray(d["omega"], dtype=state_dtype())
        self.theta = np.asarray(d["theta"], dtype=state_dtype())
        if "levels" in d:
            levels = np.asarray(d["levels"], dtype=state_dtype())
            if levels.shape != (self.depth, self.r):
                raise ValueError(
                    f"levels shape {levels.shape} != ({self.depth}, {self.r})"
                )
            self._levels[:] = levels
            # `theta` stays the inner level the operator persisted.
            self.theta = np.asarray(d["theta"], dtype=state_dtype())
        else:
            self._levels[1:] = 0
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
