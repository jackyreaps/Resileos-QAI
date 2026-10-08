"""RES-301 acceptance band and non-collinearity."""
import numpy as np

from resileos.moments import Seeds, build_moments


def packet():
    rng = np.random.default_rng(0)
    r, m, n = 4, 16, 16
    return {
        "Ub": np.sign(rng.standard_normal((m, r))),
        "Vb": np.sign(rng.standard_normal((n, r))),
        "row_s_k": rng.integers(-16, 17, size=m).astype(np.int16),
        "col_s_k": rng.integers(-16, 17, size=n).astype(np.int16),
        "lat_s_k": rng.integers(-16, 17, size=r).astype(np.int16),
        "Lambda": 0.1 * rng.standard_normal((r, r)).astype(np.float32),
        "mu": 1, "DeltaS": 0.5, "F_res": 0.0,
        "volume": 1.0, "volume_ok": True,
        "rank": 1, "schedule_index": 0,
    }


def test_cos_in_frozen_band():
    mu_hv, nu_hv = build_moments(packet(), dim=1024, seeds=Seeds.derived(42))
    cos = float(np.dot(mu_hv, nu_hv) / (np.linalg.norm(mu_hv) * np.linalg.norm(nu_hv)))
    assert 0.1 < cos < 0.5
