"""RES-300 §leCore boundary: FPE invariants."""
import numpy as np

from resileos.moments import Seeds, build_moments, fpe_encode


def test_unit_norm():
    for dim in (128, 512, 1024):
        h = fpe_encode(np.arange(16.0), dim, seed=0)
        assert h.shape == (dim,)
        assert abs(np.linalg.norm(h) - 1.0) < 1e-9


def test_empty_input():
    h = fpe_encode(np.array([]), dim=256, seed=0)
    assert h.shape == (256,)
    assert np.allclose(h, 0.0)


def test_determinism():
    x = np.arange(16.0) / 16.0
    h1 = fpe_encode(x, dim=512, seed=42)
    h2 = fpe_encode(x, dim=512, seed=42)
    assert np.array_equal(h1, h2)


def test_different_seed_decorrelates():
    x = np.arange(16.0) / 16.0
    h1 = fpe_encode(x, dim=1024, seed=0)
    h2 = fpe_encode(x, dim=1024, seed=1)
    cos = float(np.dot(h1, h2))
    assert abs(cos) < 0.1


def test_smooth_similarity_kernel():
    """Nearby inputs → high similarity; distant inputs → low similarity."""
    x = np.linspace(-1.0, 1.0, 32)
    h0 = fpe_encode(x, dim=1024, seed=0)

    x_near = x + 0.05
    x_far = x * 3.0

    h_near = fpe_encode(x_near, dim=1024, seed=0)
    h_far = fpe_encode(x_far, dim=1024, seed=0)

    cos_near = float(np.dot(h0, h_near))
    cos_far = float(np.dot(h0, h_far))

    assert cos_near > cos_far + 0.1
    assert cos_near > 0.5


def test_moment_bundle_band_preserved():
    """Integration: cos(μ_hv, ν_hv) ∈ (0.1, 0.5) with the real FPE."""
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
    for seed_base in (0, 42, 1000):
        mu_hv, nu_hv = build_moments(packet, dim=1024, seeds=Seeds.derived(seed_base))
        cos = float(np.dot(mu_hv, nu_hv)
                    / (np.linalg.norm(mu_hv) * np.linalg.norm(nu_hv)))
        assert 0.1 < cos < 0.5, f"cos={cos} for seed_base={seed_base}"
