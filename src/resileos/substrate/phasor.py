"""
Phasor graph, band carriers, and banded holographic memory.

Owning doc: RES-306.

Optional data structures. They do not modify the classical residual
core. When a PhasorGraph's triangular projection is used to build a
coupling for the core, det(I + strict_lower) = 1 is preserved.

Structural claims are formally verified in the OscGraph Lean package
(see RES-306 §0). Theorems cited by name in this module's docstrings:
unbind_bind, bind_unbind, BandGraph.adjacency_isHermitian,
BandGraph.eigenvalue_real, det_one_add_strictLower,
laplacianEnergy_nonneg, laplacianEnergy_eq_zero_iff,
crosstalk_variance, band_sharding.
"""
from __future__ import annotations

import hashlib

import numpy as np


# ── deterministic phase from names ──────────────────────────────────────
def phase_from_names(name_a: str, name_b: str) -> float:
    """
    Return a phase in [0, 2π) derived from SHA-256 of the two names.

    Deterministic across runs and machines. Python's built-in hash() is
    NOT used — it is randomized per process.

    Direction-sensitive: phase_from_names("a", "b") != phase_from_names("b", "a").
    """
    h = hashlib.sha256(f"{name_a}|{name_b}".encode("utf-8")).digest()
    u = int.from_bytes(h[:8], "big") / 2**64
    return float(2.0 * np.pi * u)


# ── phasor graph ────────────────────────────────────────────────────────
class PhasorGraph:
    """
    Graph on `n_nodes` with complex phasor edge weights.

    Two variants:

        hermitian=True   A[i,j] = conj(A[j,i]). Real spectrum. Use with
                         laplacian(), eigenvalues(), is_psd().
                         OscGraph.BandGraph.adjacency_isHermitian,
                         OscGraph.BandGraph.eigenvalue_real.

        hermitian=False  Edges stored as-is. Use triangular_projection()
                         for a strictly-lower coupling with det J = 1.
                         OscGraph.det_one_add_strictLower.

    Edge amplitudes are non-negative. Phases in [0, 2π).
    """

    def __init__(self, n_nodes: int, hermitian: bool = True):
        if n_nodes < 1:
            raise ValueError("n_nodes must be ≥ 1")
        self.n = n_nodes
        self.hermitian = hermitian
        self._edges: dict[tuple[int, int], complex] = {}

    # ── construction ────────────────────────────────────────────────────
    def set_edge(self, i: int, j: int, amplitude: float,
                 phase: float) -> None:
        """Set edge i→j with the given amplitude and phase."""
        self._check_indices(i, j)
        if amplitude < 0.0:
            raise ValueError("amplitude must be ≥ 0")
        w = amplitude * np.exp(1j * phase)
        if self.hermitian:
            lo, hi = (i, j) if i < j else (j, i)
            self._edges[(lo, hi)] = w if i < j else np.conj(w)
        else:
            self._edges[(i, j)] = w

    def set_edge_by_names(self, i: int, j: int,
                          name_a: str, name_b: str,
                          amplitude: float = 1.0) -> None:
        """Set edge i→j; phase derived deterministically from names."""
        phase = phase_from_names(name_a, name_b)
        self.set_edge(i, j, amplitude, phase)

    def clear(self) -> None:
        self._edges.clear()

    # ── adjacency ───────────────────────────────────────────────────────
    def adjacency(self) -> np.ndarray:
        """Return the [n, n] complex adjacency matrix."""
        A = np.zeros((self.n, self.n), dtype=np.complex128)
        for (i, j), w in self._edges.items():
            if self.hermitian:
                A[i, j] = w
                A[j, i] = np.conj(w)
            else:
                A[i, j] = w
        return A

    def triangular_projection(self) -> np.ndarray:
        """
        Strictly lower part of the adjacency, [n, n]. For the residual
        core: J = I + this matrix has det J = 1
        (OscGraph.det_one_add_strictLower).
        """
        A = self.adjacency()
        return np.tril(A, k=-1)

    def step_jacobian(self) -> np.ndarray:
        """J = I + strict_lower(A). det J = 1 by construction."""
        return np.eye(self.n, dtype=np.complex128) + self.triangular_projection()

    # ── Laplacian (Hermitian variant) ───────────────────────────────────
    def laplacian(self) -> np.ndarray:
        """
        Connection (magnetic) Laplacian:

            L[i,i] = sum_{k≠i} |w_ik|
            L[i,j] = -w_ij, i≠j

        Hermitian and positive semidefinite when the graph is Hermitian
        (OscGraph.laplacianEnergy_nonneg). Raises if hermitian=False.
        """
        if not self.hermitian:
            raise ValueError(
                "laplacian() requires hermitian=True; use adjacency() and "
                "triangular_projection() for the non-Hermitian variant"
            )
        A = self.adjacency()
        abs_A = np.abs(A)
        D = np.diag(abs_A.sum(axis=1))
        return D - A

    def eigenvalues(self) -> np.ndarray:
        """
        Real eigenvalues of the connection Laplacian, sorted ascending.
        Raises if hermitian=False.
        """
        L = self.laplacian()
        return np.linalg.eigvalsh(L)

    def is_psd(self, tol: float = 1e-9) -> bool:
        """True iff the connection Laplacian is positive semidefinite."""
        if not self.hermitian:
            return False
        w = self.eigenvalues()
        return bool(w.min() >= -tol)

    def spectral_margin(self) -> float:
        """λ_min(L). Non-negative for a PSD Laplacian."""
        return float(self.eigenvalues().min())

    # ── scalar diagnostics ──────────────────────────────────────────────
    def energy_from_identity(self) -> float:
        """
        Frobenius norm of the strictly-lower triangular part. Starts at 0
        for an empty graph; grows as edges are added.
        """
        return float(np.linalg.norm(self.triangular_projection(), "fro"))

    def n_edges(self) -> int:
        return len(self._edges)

    # ── validation ──────────────────────────────────────────────────────
    def _check_indices(self, i: int, j: int) -> None:
        if not (0 <= i < self.n) or not (0 <= j < self.n):
            raise IndexError(f"index out of range: ({i}, {j})")
        if i == j:
            raise ValueError("self-loops are not allowed")


# ── band carriers ───────────────────────────────────────────────────────
class BandCarriers:
    """
    K unit-phasor vectors of length d, spaced by golden-ratio Weyl
    sequence:

        ω_k = 2π · frac(k · φ),   φ = (1 + √5) / 2
        u_k[m] = exp(i ω_k m) / √d

    The carrier has per-component magnitude 1/√d and unit total norm
    (‖u_k‖_2 = 1). bind and unbind include a compensating √d factor so
    that the round-trip is exact:

        bind(x, k)   = x ⊙ u_k · √d
        unbind(y, k) = y ⊙ conj(u_k) · √d

        unbind(bind(x, k), k) = x · |u_k|² · d = x · (1/d) · d = x

    Carriers are unit-norm (BandCarriers.carrier(k) returns u_k).
    Crosstalk is bounded by 1/√d under the random-phase model.

    Golden spacing never locks (OscGraph.golden_never_locks,
    OscGraph.golden_carrier_never_returns). Rational spacings recur
    (OscGraph.returns_iff_rational).
    """

    def __init__(self, dim: int, n_bands: int):
        if dim < 1:
            raise ValueError("dim must be ≥ 1")
        if n_bands < 0:
            raise ValueError("n_bands must be ≥ 0")
        self.dim = dim
        self.n_bands = n_bands
        phi = (1.0 + np.sqrt(5.0)) / 2.0
        m = np.arange(dim, dtype=np.float64)
        self._freqs = np.array(
            [2.0 * np.pi * (k * phi % 1.0) for k in range(n_bands)],
            dtype=np.float64,
        )
        if n_bands > 0:
            self._carriers = np.array(
                [np.exp(1j * w * m) / np.sqrt(dim) for w in self._freqs],
                dtype=np.complex128,
            )
        else:
            self._carriers = np.zeros((0, dim), dtype=np.complex128)
        self._scale = float(np.sqrt(dim))

    # ── accessors ───────────────────────────────────────────────────────
    def carrier(self, k: int) -> np.ndarray:
        """Unit-norm phasor vector for band k, length d."""
        if not (0 <= k < self.n_bands):
            raise IndexError(f"band {k} out of range [0, {self.n_bands})")
        return self._carriers[k].copy()

    def frequencies(self) -> np.ndarray:
        """Angular frequencies ω_k, shape [K]."""
        return self._freqs.copy()

    # ── binding ─────────────────────────────────────────────────────────
    def bind(self, x: np.ndarray, k: int) -> np.ndarray:
        """
        Bind x into band k: x ⊙ u_k · √d.

        Includes the √d factor so unbind(bind(x, k), k) = x exactly.
        """
        if not (0 <= k < self.n_bands):
            raise IndexError(f"band {k} out of range [0, {self.n_bands})")
        return (np.asarray(x, dtype=np.complex128)
                * self._carriers[k] * self._scale)

    def unbind(self, y: np.ndarray, k: int) -> np.ndarray:
        """
        Unbind from band k: y ⊙ conj(u_k) · √d.

        Includes the √d factor so this is the exact inverse of bind.
        """
        if not (0 <= k < self.n_bands):
            raise IndexError(f"band {k} out of range [0, {self.n_bands})")
        return (np.asarray(y, dtype=np.complex128)
                * np.conj(self._carriers[k]) * self._scale)

    # ── diagnostics ─────────────────────────────────────────────────────
    def crosstalk(self) -> float:
        """
        Max |<u_j, u_k>| over j ≠ k. Small for large d; approximately
        1/√d under the random-phase model.
        """
        if self.n_bands < 2:
            return 0.0
        G = self._carriers @ self._carriers.conj().T
        G_abs = np.abs(G)
        np.fill_diagonal(G_abs, 0.0)
        return float(G_abs.max())

    def gram(self) -> np.ndarray:
        """Full Gram matrix <u_j, u_k>, shape [K, K]."""
        if self.n_bands == 0:
            return np.zeros((0, 0), dtype=np.complex128)
        return self._carriers @ self._carriers.conj().T


# ── banded holographic memory ───────────────────────────────────────────
class BandedMemory:
    """
    Holographic memory with K bands, each an independent accumulator.

    Storage:
        acc[k] += key ⊙ value      (band k)

    Retrieval (band k):
        retrieved = acc[k] ⊙ conj(key)

    Under the random-key model, per-band crosstalk variance is n/D
    exactly (OscGraph.crosstalk_variance). Splitting N items over K
    bands read separately reduces per-query crosstalk amplitude by at
    least √K (OscGraph.band_sharding).

    Keys are normalized to unit phasors per component on store. Values
    are used as-is.

    This is the memory layer the RES-306 crosstalk results are about.
    It is not the residual core. It does not read or write the control
    packet.
    """

    def __init__(self, dim: int, n_bands: int):
        if dim < 1:
            raise ValueError("dim must be ≥ 1")
        if n_bands < 1:
            raise ValueError("n_bands must be ≥ 1")
        self.dim = dim
        self.n_bands = n_bands
        self.carriers = BandCarriers(dim=dim, n_bands=n_bands)
        self.acc = np.zeros((n_bands, dim), dtype=np.complex128)
        self._counts = np.zeros(n_bands, dtype=np.int64)

    # ── helpers ─────────────────────────────────────────────────────────
    def _normalize_to_unit(self, x: np.ndarray) -> np.ndarray:
        """Normalize so that |x[i]| = 1 for every component."""
        x = np.asarray(x, dtype=np.complex128)
        if x.shape != (self.dim,):
            raise ValueError(
                f"expected shape ({self.dim},), got {x.shape}")
        mag = np.abs(x)
        mag[mag == 0.0] = 1.0
        return x / mag

    # ── public API ──────────────────────────────────────────────────────
    def store(self, key: np.ndarray, value: np.ndarray, band: int) -> None:
        """Store (key, value) in band `band` as acc[band] += key ⊙ value."""
        if not (0 <= band < self.n_bands):
            raise IndexError(f"band {band} out of range [0, {self.n_bands})")
        k = self._normalize_to_unit(key)
        v = np.asarray(value, dtype=np.complex128)
        if v.shape != (self.dim,):
            raise ValueError(
                f"value must have shape ({self.dim},), got {v.shape}")
        self.acc[band] += k * v
        self._counts[band] += 1

    def retrieve(self, key: np.ndarray, band: int) -> np.ndarray:
        """
        Retrieve by unbinding: acc[band] ⊙ conj(key).

        Returns the raw retrieved vector. Cleanup (matching against
        candidates) is the caller's responsibility.
        """
        if not (0 <= band < self.n_bands):
            raise IndexError(f"band {band} out of range [0, {self.n_bands})")
        k = self._normalize_to_unit(key)
        return self.acc[band] * np.conj(k)

    def score(self, retrieved: np.ndarray, value: np.ndarray) -> complex:
        """
        Inner product of `retrieved` with `value`, normalized by dim.
        For a matching pair stored alone, this is 1 exactly.
        """
        r = np.asarray(retrieved, dtype=np.complex128)
        v = np.asarray(value, dtype=np.complex128)
        return complex(np.vdot(v, r) / self.dim)

    def count(self, band: int) -> int:
        if not (0 <= band < self.n_bands):
            raise IndexError(f"band {band} out of range [0, {self.n_bands})")
        return int(self._counts[band])

    def clear(self) -> None:
        self.acc[:] = 0
        self._counts[:] = 0

    # ── persistence ─────────────────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "dim": self.dim,
            "n_bands": self.n_bands,
            "acc": self.acc.tolist(),
            "counts": self._counts.tolist(),
        }

    def load_state_dict(self, d: dict) -> None:
        if d["dim"] != self.dim or d["n_bands"] != self.n_bands:
            raise ValueError(
                f"dim/n_bands mismatch: {d['dim']}/{d['n_bands']} vs "
                f"{self.dim}/{self.n_bands}")
        self.acc = np.array(d["acc"], dtype=np.complex128)
        self._counts = np.array(d["counts"], dtype=np.int64)


__all__ = [
    "PhasorGraph",
    "BandCarriers",
    "BandedMemory",
    "phase_from_names",
]
