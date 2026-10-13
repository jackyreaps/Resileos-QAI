"""Tests for RES-306 phasor graph, band carriers, and banded memory."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.phasor import (
    PhasorGraph, BandCarriers, BandedMemory, phase_from_names,
)


# ── phase provenance ────────────────────────────────────────────────────
def test_phase_deterministic():
    a = phase_from_names("Zeus", "parent_of")
    b = phase_from_names("Zeus", "parent_of")
    assert a == b
    assert 0.0 <= a < 2.0 * np.pi


def test_phase_differs_for_different_names():
    assert phase_from_names("Zeus", "parent_of") != phase_from_names("Zeus", "domain")


def test_phase_direction_sensitive():
    assert phase_from_names("Zeus", "parent_of") != phase_from_names("parent_of", "Zeus")


# ── hermitian variant ───────────────────────────────────────────────────
def test_hermitian_adjacency():
    g = PhasorGraph(4, hermitian=True)
    g.set_edge(0, 1, amplitude=0.5, phase=0.3)
    g.set_edge(1, 3, amplitude=0.8, phase=1.1)
    A = g.adjacency()
    assert np.allclose(A, A.conj().T, atol=1e-12)


def test_hermitian_laplacian_psd():
    g = PhasorGraph(5, hermitian=True)
    for i in range(5):
        for j in range(i + 1, 5):
            g.set_edge(i, j, amplitude=0.4, phase=float(i + j) * 0.7)
    assert g.is_psd()
    L = g.laplacian()
    assert np.allclose(L, L.conj().T, atol=1e-12)


def test_hermitian_eigenvalues_real():
    g = PhasorGraph(6, hermitian=True)
    for i in range(6):
        for j in range(i + 1, 6):
            g.set_edge(i, j, amplitude=1.0,
                       phase=phase_from_names(f"n{i}", f"n{j}"))
    w = g.eigenvalues()
    assert w.dtype == np.float64
    assert w.min() >= -1e-9


def test_empty_hermitian_laplacian_is_zero():
    g = PhasorGraph(4, hermitian=True)
    assert np.allclose(g.laplacian(), 0.0)
    assert g.is_psd()


def test_laplacian_requires_hermitian():
    g = PhasorGraph(3, hermitian=False)
    g.set_edge(0, 1, 0.5, 0.2)
    with pytest.raises(ValueError):
        g.laplacian()


# ── triangular variant ──────────────────────────────────────────────────
def test_triangular_jacobian_det_one():
    g = PhasorGraph(5, hermitian=False)
    for i in range(5):
        for j in range(i + 1, 5):
            g.set_edge(j, i, amplitude=0.6, phase=float(i * j) * 0.4)
    J = g.step_jacobian()
    det = np.linalg.det(J)
    assert np.isclose(det.real, 1.0, atol=1e-10)
    assert np.isclose(det.imag, 0.0, atol=1e-10)


def test_triangular_projection_is_lower():
    g = PhasorGraph(4, hermitian=False)
    g.set_edge(2, 0, amplitude=0.7, phase=0.3)
    T = g.triangular_projection()
    assert np.allclose(np.triu(T, k=0), 0.0)
    assert not np.isclose(T[2, 0], 0.0)


def test_set_edge_by_names_deterministic():
    g1 = PhasorGraph(3, hermitian=True)
    g2 = PhasorGraph(3, hermitian=True)
    g1.set_edge_by_names(0, 1, "Zeus", "Ares")
    g2.set_edge_by_names(0, 1, "Zeus", "Ares")
    assert np.allclose(g1.adjacency(), g2.adjacency())


# ── validation ──────────────────────────────────────────────────────────
def test_self_loop_rejected():
    with pytest.raises(ValueError, match="self-loops"):
        PhasorGraph(3).set_edge(1, 1, amplitude=0.5, phase=0.0)


def test_out_of_range_rejected():
    with pytest.raises(IndexError):
        PhasorGraph(3).set_edge(0, 5, amplitude=0.5, phase=0.0)


def test_negative_amplitude_rejected():
    with pytest.raises(ValueError, match="amplitude"):
        PhasorGraph(3).set_edge(0, 1, amplitude=-0.1, phase=0.0)


# ── band carriers ───────────────────────────────────────────────────────
def test_carrier_unit_norm():
    bc = BandCarriers(dim=512, n_bands=8)
    for k in range(8):
        assert np.isclose(np.linalg.norm(bc.carrier(k)), 1.0, atol=1e-9)


def test_bind_unbind_roundtrip():
    bc = BandCarriers(dim=256, n_bands=4)
    rng = np.random.default_rng(0)
    x = rng.standard_normal(256) + 1j * rng.standard_normal(256)
    for k in range(4):
        assert np.allclose(bc.unbind(bc.bind(x, k), k), x, atol=1e-10)


def test_carrier_crosstalk_small():
    bc = BandCarriers(dim=1024, n_bands=8)
    assert bc.crosstalk() < 0.2


def test_carrier_frequencies_golden_spacing():
    bc = BandCarriers(dim=128, n_bands=5)
    freqs = bc.frequencies()
    phi = (1 + np.sqrt(5)) / 2
    assert np.isclose(freqs[0], 0.0)
    for k in range(5):
        assert np.isclose(freqs[k], 2 * np.pi * (k * phi % 1.0))


def test_zero_bands_ok():
    bc = BandCarriers(dim=64, n_bands=0)
    assert bc.n_bands == 0
    assert np.isclose(bc.crosstalk(), 0.0)


def test_band_index_out_of_range():
    with pytest.raises(IndexError):
        BandCarriers(dim=64, n_bands=2).carrier(5)


# ── banded memory: crosstalk and sharding ───────────────────────────────
def _random_unit_phasor(dim: int, rng: np.random.Generator) -> np.ndarray:
    """Uniform random unit phasors, one per component."""
    theta = rng.uniform(0.0, 2.0 * np.pi, size=dim)
    return np.exp(1j * theta).astype(np.complex128)


def test_memory_single_item_exact():
    """One item stored: score against its own value is exactly 1."""
    D = 512
    mem = BandedMemory(dim=D, n_bands=1)
    rng = np.random.default_rng(1)
    key = _random_unit_phasor(D, rng)
    val = _random_unit_phasor(D, rng)
    mem.store(key, val, band=0)
    retrieved = mem.retrieve(key, band=0)
    s = mem.score(retrieved, val)
    assert np.isclose(s.real, 1.0, atol=1e-10)
    assert np.isclose(s.imag, 0.0, atol=1e-10)


def test_memory_crosstalk_variance_matches_theory():
    """
    E |noise|^2 should approximate n / D, where n is the number of
    other items stored (OscGraph.crosstalk_variance).

    Checked within a factor of 2 across 200 trials.
    """
    D = 4096
    n = 16
    trials = 200
    rng = np.random.default_rng(42)

    total_noise_sq = 0.0
    for _ in range(trials):
        mem = BandedMemory(dim=D, n_bands=1)
        key0 = _random_unit_phasor(D, rng)
        val0 = _random_unit_phasor(D, rng)
        mem.store(key0, val0, band=0)
        for _ in range(n):
            mem.store(_random_unit_phasor(D, rng),
                      _random_unit_phasor(D, rng), band=0)
        retrieved = mem.retrieve(key0, band=0)
        s = mem.score(retrieved, val0)
        noise = s - 1.0
        total_noise_sq += abs(noise) ** 2

    empirical = total_noise_sq / trials
    theoretical = n / D
    assert 0.5 * theoretical < empirical < 2.0 * theoretical, (
        f"empirical {empirical:.6e} not within 2x of theoretical "
        f"{theoretical:.6e}")


def test_band_sharding_reduces_per_band_crosstalk():
    """
    Same total items N, split over K bands, has per-band crosstalk
    variance approximately 1/K of a single shared memory
    (OscGraph.band_sharding).
    """
    D = 4096
    N_total = 32
    K = 4
    trials = 200
    rng = np.random.default_rng(7)

    shared_noise_sq = 0.0
    for _ in range(trials):
        mem = BandedMemory(dim=D, n_bands=1)
        key0 = _random_unit_phasor(D, rng)
        val0 = _random_unit_phasor(D, rng)
        mem.store(key0, val0, band=0)
        for _ in range(N_total):
            mem.store(_random_unit_phasor(D, rng),
                      _random_unit_phasor(D, rng), band=0)
        retrieved = mem.retrieve(key0, band=0)
        shared_noise_sq += abs(mem.score(retrieved, val0) - 1.0) ** 2
    shared_var = shared_noise_sq / trials

    per_band = N_total // K
    banded_noise_sq = 0.0
    for _ in range(trials):
        mem = BandedMemory(dim=D, n_bands=K)
        key0 = _random_unit_phasor(D, rng)
        val0 = _random_unit_phasor(D, rng)
        mem.store(key0, val0, band=0)
        for _ in range(per_band):
            mem.store(_random_unit_phasor(D, rng),
                      _random_unit_phasor(D, rng), band=0)
        for b in range(1, K):
            for _ in range(per_band):
                mem.store(_random_unit_phasor(D, rng),
                          _random_unit_phasor(D, rng), band=b)
        retrieved = mem.retrieve(key0, band=0)
        banded_noise_sq += abs(mem.score(retrieved, val0) - 1.0) ** 2
    banded_var = banded_noise_sq / trials

    ratio = shared_var / banded_var
    assert ratio > K / 2.0, (
        f"variance ratio {ratio:.2f} not > K/2 = {K/2}")


def test_memory_band_index_validation():
    mem = BandedMemory(dim=64, n_bands=2)
    rng = np.random.default_rng(0)
    key = _random_unit_phasor(64, rng)
    val = _random_unit_phasor(64, rng)
    with pytest.raises(IndexError):
        mem.store(key, val, band=5)
    with pytest.raises(IndexError):
        mem.retrieve(key, band=5)


def test_memory_shape_validation():
    mem = BandedMemory(dim=64, n_bands=2)
    rng = np.random.default_rng(0)
    short = _random_unit_phasor(32, rng)
    full = _random_unit_phasor(64, rng)
    with pytest.raises(ValueError):
        mem.store(short, full, band=0)
    with pytest.raises(ValueError):
        mem.store(full, short, band=0)


def test_memory_persistence_roundtrip():
    D = 128
    mem = BandedMemory(dim=D, n_bands=2)
    rng = np.random.default_rng(0)
    for _ in range(3):
        mem.store(_random_unit_phasor(D, rng),
                  _random_unit_phasor(D, rng), band=0)
    for _ in range(5):
        mem.store(_random_unit_phasor(D, rng),
                  _random_unit_phasor(D, rng), band=1)
    d = mem.state_dict()
    mem2 = BandedMemory(dim=D, n_bands=2)
    mem2.load_state_dict(d)
    assert np.allclose(mem.acc, mem2.acc)
    assert mem.count(0) == mem2.count(0)
    assert mem.count(1) == mem2.count(1)


# ── interaction ─────────────────────────────────────────────────────────
def test_phasor_graph_with_hash_phases_and_carriers():
    """Combined use: graph phases from names, memory bands from carriers."""
    g = PhasorGraph(4, hermitian=True)
    entities = ["Zeus", "Ares", "Athena", "Hera"]
    for i in range(4):
        for j in range(i + 1, 4):
            g.set_edge_by_names(i, j, entities[i], entities[j], amplitude=1.0)
    assert g.is_psd()

    bc = BandCarriers(dim=128, n_bands=4)
    rng = np.random.default_rng(1)
    x = rng.standard_normal(128).astype(np.complex128)
    for k in range(4):
        assert np.allclose(bc.unbind(bc.bind(x, k), k), x)
