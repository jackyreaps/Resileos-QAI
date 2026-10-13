"""
Phasor graph, band carriers, and banded holographic memory.

Owning doc: RES-306.

Optional data structures. They do not modify the classical residual
core. When a PhasorGraph's triangular projection is used to build a
coupling for the core, det(I + strict_lower) = 1 is preserved.

Structural claims are formally verified in the OscGraph Lean package
(see RES-306 §0).
"""
from __future__ import annotations

import hashlib

import numpy as np


def phase_from_names(name_a: str, name_b: str) -> float:
    """
    Return a phase in [0, 2π) derived from SHA-256 of the two names.

    Deterministic across runs and machines. Direction-sensitive.
    """
    h = hashlib.sha256(f"{name_a}|{name_b}".encode("utf-8")).digest()
    u = int.from_bytes(h[:8], "big") / 2**64
    return float(2.0 * np.pi * u)


class PhasorGraph:
    """
    Graph on `n_nodes` with complex phasor edge weights.

    Two variants:

        hermitian=True   A[i,j] = conj(A[j,i]). Real spectrum.
        hermitian=False  Edges stored as-is. Use triangular_projection()
                         for a strictly-lower coupling with det J = 1.

    Edge phases can be updated externally via apply_phase_context(theta),
    which maps the theta vector onto edge indices. Used by ResidualCore
    when a phasor graph is attached as the core coupling.
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
        phase = phase_from_names(name_a, name_b)
        self.set_edge(i, j, amplitude, phase)

    def clear(self) -> None:
        self._edges.clear()

    # ── phase context ───────────────────────────────────────────────────
    def apply_phase_context(self, theta: np.ndarray) -> None:
        """
        Update every edge's phase from a theta vector. Edge (i, j) uses
        theta[(i * n + j) % len(theta)]. Amplitudes are preserved.

        Called by ResidualCore each step when this graph is attached,
        so the coupling oscillates with the non-conservative operator's
        phase dynamics.
        """
        theta = np.asarray(theta, dtype=np.float64)
        if theta.size == 0:
            return
        for (i, j), w in list(self._edges.items()):
            amp = abs(w)
            idx = (i * self.n + j) % theta.size
            new_phase = float(theta[idx])
            self._edges[(i, j)] = amp * np.exp(1j * new_phase)

    # ── adjacency ───────────────────────────────────────────────────────
    def adjacency(self) -> np.ndarray:
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
        core: J = I + this matrix has det J = 1.
        """
        A = self.adjacency()
        return np.tril(A, k=-1)

    def step_jacobian(self) -> np.ndarray:
        return np.eye(self.n, dtype=np.complex128) + self.triangular_projection()

    # ── Laplacian ───────────────────────────────────────────────────────
    def laplacian(self) -> np.ndarray:
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
        return np.linalg.eigvalsh(self.laplacian())

    def is_psd(self, tol: float = 1e-9) -> bool:
        if not self.hermitian:
            return False
        return bool(self.eigenvalues().min() >= -tol)

    def spectral_margin(self) -> float:
        return float(self.eigenvalues().min())

    def energy_from_identity(self) -> float:
        return float(np.linalg.norm(self.triangular_projection(), "fro"))

    def n_edges(self) -> int:
        return len(self._edges)

    def _check_indices(self, i: int, j: int) -> None:
        if not (0 <= i < self.n) or not (0 <= j < self.n):
            raise IndexError(f"index out of range: ({i}, {j})")
        if i == j:
            raise ValueError("self-loops are not allowed")


class BandCarriers:
    """
    K unit-phasor vectors of length d, spaced by golden-ratio Weyl
    sequence:

        ω_k = 2π · frac(k · φ),   φ = (1 + √5) / 2
        u_k[m] = exp(i ω_k m) / √d

    The carrier has per-component magnitude 1/√d and unit total norm.
    bind and unbind include a compensating √d factor so that
    unbind(bind(x, k), k) = x exactly.
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

    def carrier(self, k: int) -> np.ndarray:
        if not (0 <= k < self.n_bands):
            raise IndexError(f"band {k} out of range [0, {self.n_bands})")
        return self._carriers[k].copy()

    def frequencies(self) -> np.ndarray:
        return self._freqs.copy()

    def bind(self, x: np.ndarray, k: int) -> np.ndarray:
        if not (0 <= k < self.n_bands):
            raise IndexError(f"band {k} out of range [0, {self.n_bands})")
        return (np.asarray(x, dtype=np.complex128)
                * self._carriers[k] * self._scale)

    def unbind(self, y: np.ndarray, k: int) -> np.ndarray:
        if not (0 <= k < self.n_bands):
            raise IndexError(f"band {k} out of range [0, {self.n_bands})")
        return (np.asarray(y, dtype=np.complex128)
                * np.conj(self._carriers[k]) * self._scale)

    def crosstalk(self) -> float:
        if self.n_bands < 2:
            return 0.0
        G = self._carriers @ self._carriers.conj().T
        G_abs = np.abs(G)
        np.fill_diagonal(G_abs, 0.0)
        return float(G_abs.max())

    def gram(self) -> np.ndarray:
        if self.n_bands == 0:
            return np.zeros((0, 0), dtype=np.complex128)
        return self._carriers @ self._carriers.conj().T


class BandedMemory:
    """
    Holographic memory with K bands, each an independent accumulator.

    Under the random-key model, per-band crosstalk variance is n/D
    exactly (OscGraph.crosstalk_variance). Splitting N items over K
    bands read separately reduces per-query crosstalk amplitude by at
    least √K (OscGraph.band_sharding).
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

    def _normalize_to_unit(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.complex128)
        if x.shape != (self.dim,):
            raise ValueError(
                f"expected shape ({self.dim},), got {x.shape}")
        mag = np.abs(x)
        mag[mag == 0.0] = 1.0
        return x / mag

    def store(self, key: np.ndarray, value: np.ndarray, band: int) -> None:
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
        if not (0 <= band < self.n_bands):
            raise IndexError(f"band {band} out of range [0, {self.n_bands})")
        k = self._normalize_to_unit(key)
        return self.acc[band] * np.conj(k)

    def score(self, retrieved: np.ndarray, value: np.ndarray) -> complex:
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
