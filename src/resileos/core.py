"""
Classical residual core: the sole producer of the control packet.
Owning doc: RES-200.

Never receives gradients (RES-401). Deterministic given (W, mu, F_res,
thresholds) and internal state.

Volume-preservation invariant:
    J = diag(D) + coupling, with det(D) = 1.
    det(J) = det(D) = 1 exactly.
    When D = I and coupling = strict_lower(Lambda), this reduces to the
    original I + strict_lower(Lambda) case.

Residual stack:
    With n_residual_layers > 1, the step applies the bipolar
    factorization repeatedly, each layer modeling the residual of the
    previous. The full reconstruction is available as
    `core.last_reconstruction`. The packet emits layer 0's factors
    (schema unchanged, RES-201 frozen).

Phase wiring (optional):
    If a PhasorGraph is attached, its edge phases are driven by the
    non-conservative operator's theta on every step, and its triangular
    projection becomes the coupling used by the scar update. This makes
    the coupling oscillate with the dynamics. It does not affect
    `_factorize`, so it does not affect the compression number.
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
    # Residual stack depth. 1 reproduces the previous single-layer
    # behavior; 12 matches the earlier compression measurement (~70%).
    n_residual_layers: int = 12


class ResidualCore:
    """
    Deterministic residual-compensation producer (RES-200).

    Optional keyword arguments:
        non_conservative      enable the non-conservative operator
        nc_gamma_max          max |g_i| deviation in log space
        nc_phase_max          max |theta_i| in radians
        nc_decay              smoothing on g
        phasor_graph          optional PhasorGraph whose triangular
                              projection becomes the coupling. Edge
                              phases are updated from theta each step.
                              Graph must be built with non-hermitian
                              edges (i > j) so triangular_projection()
                              is strict-lower.
    """

    def __init__(self, cfg: CoreConfig, seed: int = 0,
                 non_conservative: bool = False,
                 nc_gamma_max: float = 0.5,
                 nc_phase_max: float = 0.4,
                 nc_decay: float = 0.9,
                 phasor_graph=None) -> None:
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
        self._phasor_graph = phasor_graph
        self._last_reconstruction: np.ndarray | None = None

    # ── internals ─────────────────────────────────────────────────────
    def _factorize(self, W):
        U = W @ self._Vb0.T
        V = self._Ub0.T @ W
        Ub = np.sign(U); Ub[Ub == 0] = 1.0
        Vb = np.sign(V); Vb[Vb == 0] = 1.0
        return Ub.astype(np.float32), Vb.astype(np.float32)

    def _reconstruct_layer(self, Ub, Vb, R):
        """Rescale the layer's reconstruction to best fit R in L2."""
        P = Ub @ Vb
        denom = float(np.sum(P * P)) + 1e-12
        s = float(np.sum(R * P)) / denom
        return s * P, s

    def _factorize_residual_stack(self, W):
        """
        Apply the bipolar factorization n_residual_layers times, each
        layer fitting the residual of the previous. Returns
        (layers, W_hat_total). layers[0] is the primary factorization
        that goes into the packet.
        """
        R = W.copy()
        W_hat_total = np.zeros_like(W)
        layers: list[tuple[np.ndarray, np.ndarray, float]] = []
        for _ in range(self.cfg.n_residual_layers):
            Ub_l, Vb_l = self._factorize(R)
            W_hat_l, s_l = self._reconstruct_layer(Ub_l, Vb_l, R)
            R = R - W_hat_l
            W_hat_total = W_hat_total + W_hat_l
            layers.append((Ub_l, Vb_l, s_l))
        return layers, W_hat_total

    def _scar_update(self, M_lat, F_res, DeltaS, mu):
        self._nonconservative.update(F_res=F_res, DeltaS=DeltaS, mu=mu)
        D = self._nonconservative.diagonal()

        # Coupling: either the phasor graph (if attached) or the strict
        # lower part of the current scar.
        if self._phasor_graph is not None:
            theta = self._nonconservative.theta
            self._phasor_graph.apply_phase_context(theta)
            graph_coupling = self._phasor_graph.triangular_projection()
            # Element-wise modulate Lambda's strict-lower by the graph's
            # complex edge weights.
            coupling = _strict_lower(self._Lambda.astype(np.complex128)) * graph_coupling
        else:
            coupling = _strict_lower(self._Lambda.astype(np.complex128))

        Lambda_eff = np.diag(D) + coupling
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
        J = diag(D) + coupling. det(J) = prod(D) = 1 by construction.
        In conservative mode (D = I), reduces to det(I + strict_lower) = 1.
        """
        D = self._nonconservative.diagonal()
        if self._phasor_graph is not None:
            graph_coupling = self._phasor_graph.triangular_projection()
            coupling = _strict_lower(Lambda.astype(np.complex128)) * graph_coupling
        else:
            coupling = _strict_lower(Lambda.astype(np.complex128))
        J = np.diag(D) + coupling
        det = complex(np.linalg.det(J))
        log_abs = abs(np.log10(abs(det) + 1e-300))
        return det, bool(log_abs < 1e-9)

    # ── public API ────────────────────────────────────────────────────
    def step(self, W, mu=0, F_res=0.0, theta_hi=0.0, theta_lo=0.0,
             DeltaS=0.0, sigma1_gate=False, sigma1_action="NONE",
             version="1.0.0", factors=None) -> Packet:
        W = np.asarray(W, dtype=np.float64)
        if W.shape != (self.cfg.m, self.cfg.n):
            raise ValueError(
                f"W must be ({self.cfg.m}, {self.cfg.n}), got {W.shape}")

        if factors is not None:
            # External factors: single-layer override (used by training).
            Ub_ext, Vb_ext = factors
            Ub = np.asarray(Ub_ext, dtype=np.float32)
            Vb = np.asarray(Vb_ext, dtype=np.float32)
            if Ub.shape != (self.cfg.m, self.cfg.r) or \
               Vb.shape != (self.cfg.r, self.cfg.n):
                raise ValueError(
                    f"factors shape mismatch: Ub {Ub.shape}, Vb {Vb.shape}")
            W_hat, _ = self._reconstruct_layer(Ub, Vb, W)
            R = W - W_hat
            primary_Ub, primary_Vb = Ub, Vb
        else:
            layers, W_hat = self._factorize_residual_stack(W)
            R = W - W_hat
            primary_Ub, primary_Vb, _ = layers[0]

        self._last_reconstruction = W_hat.copy()

        M_lat = (primary_Ub.T @ R @ primary_Vb.T) / float(self.cfg.m * self.cfg.n)
        self._Lambda = self._scar_update(M_lat, F_res=F_res,
                                         DeltaS=DeltaS, mu=int(mu))

        row_s, col_s, lat_s = self._residual_scales(R, primary_Ub, primary_Vb)
        volume, volume_ok = self._volume_guard(self._Lambda)
        D = self._nonconservative.diagonal()

        mu_new, _ = ParityState(
            mu=int(mu),
            theta_hi=float(theta_hi),
            theta_lo=float(theta_lo),
        ).update(float(F_res))

        packet = Packet(
            version=version,
            Ub=primary_Ub,
            Vb=primary_Vb,
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

    @property
    def last_reconstruction(self) -> np.ndarray | None:
        """
        Full reconstruction of the most recent step, including all
        residual layers. None before the first step.

        The packet emits only layer 0's factors (RES-201 frozen). This
        property gives access to the stacked approximation the core
        actually computed, which is what the compression gate measures.
        """
        return self._last_reconstruction


# ── helper: build a coupling graph ──────────────────────────────────────
def build_coupling_graph(r: int, seed: int = 0):
    """
    Build a non-hermitian PhasorGraph on r nodes with strict-lower
    edges. Suitable as the `phasor_graph` argument to ResidualCore.

    Import is local so this module does not require the substrate
    package to be importable.
    """
    from .substrate.phasor import PhasorGraph

    g = PhasorGraph(r, hermitian=False)
    rng = np.random.default_rng(seed)
    for i in range(1, r):
        for j in range(i):
            g.set_edge(i, j, amplitude=1.0,
                       phase=float(rng.uniform(0.0, 2.0 * np.pi)))
    return g
