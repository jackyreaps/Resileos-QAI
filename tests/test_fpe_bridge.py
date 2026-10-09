"""Contract tests for the leCore FPE adapter (RES-300 §leCore boundary)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.fpe import (
    fpe_encode_bipolar,
    backend_name,
    LECORE_AVAILABLE,
)


def test_backend_reported():
    """Backend must be one of the two known values."""
    assert backend_name() in ("lecore", "inhouse")


def test_signature_and_dtype():
    """Contract: (x, dim, seed) -> bipolar int8 of length dim."""
    h = fpe_encode_bipolar(np.arange(8.0), 256, seed=0)
    assert h.shape == (256,)
    assert h.dtype == np.int8
    assert set(np.unique(h).tolist()) <= {-1, 1}


def test_unit_norm_bipolar():
    """For a bipolar vector of length D, ||h||_2 == sqrt(D)."""
    D = 512
    h = fpe_encode_bipolar(np.arange(8.0), D, seed=0)
    assert np.isclose(np.linalg.norm(h), np.sqrt(D), atol=1e-6)


def test_empty_input():
    h = fpe_encode_bipolar(np.array([]), 128, seed=0)
    assert h.shape == (128,)
    # Empty input -> zeros from encoder -> quantized to bipolar.
    # The zero-handling path makes it deterministic, not all-zero.


def test_determinism():
    x = np.arange(16.0) / 16.0
    a = fpe_encode_bipolar(x, 512, seed=42)
    b = fpe_encode_bipolar(x, 512, seed=42)
    assert np.array_equal(a, b)


def test_different_seeds_decorrelate():
    x = np.arange(16.0) / 16.0
    a = fpe_encode_bipolar(x, 1024, seed=0).astype(np.float64)
    b = fpe_encode_bipolar(x, 1024, seed=1).astype(np.float64)
    cos = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
    assert abs(cos) < 0.15


def test_similarity_is_smooth():
    """Nearby inputs should correlate more than distant inputs."""
    x = np.linspace(-1.0, 1.0, 32)
    h0 = fpe_encode_bipolar(x, 1024, seed=0).astype(np.float64)
    h_near = fpe_encode_bipolar(x + 0.02, 1024, seed=0).astype(np.float64)
    h_far = fpe_encode_bipolar(x * 3.0, 1024, seed=0).astype(np.float64)

    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    assert cos(h0, h_near) > cos(h0, h_far)


def test_moment_bundle_band_still_holds():
    """RES-301 §2 acceptance band survives the adapter."""
    from resileos.moments import Seeds, build_moments

    rng = np.random.default_rng(0)
    r, m, n = 4, 16, 16
    packet = {
        "Ub": np.sign(rng.standard_normal((m, r))),
        "Vb": np.sign(rng.standard_normal((n, r))),
        "row_s_k": rng.integers(-16, 17, size=m).astype(np.int16),
        "col_s_k": rng.integers(-16, 17, size=n).astype(np.int16),
        "lat_s_k": rng.integers(-16, 17, size=r).astype(np.int16),
        "Lambda": 0.1 * rng.standard_normal((r, r)).astype(np.float32),
        "mu": 1, "DeltaS": 0.5,
    }
    mu_hv, nu_hv = build_moments(packet, dim=1024, seeds=Seeds.derived(42))
    cos = float(np.dot(mu_hv, nu_hv)
                / (np.linalg.norm(mu_hv) * np.linalg.norm(nu_hv) + 1e-12))
    assert 0.1 < cos < 0.5, f"cos={cos} out of band under {backend_name()} backend"
