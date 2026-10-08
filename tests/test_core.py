"""RES-200 classical residual core: packet emission and invariants."""
import numpy as np

from resileos.core import CoreConfig, ResidualCore, prime_tower
from resileos.packet import packet_hash, K_MIN, K_MAX


def _cfg():
    return CoreConfig(m=16, n=16, r=4)


def _W(seed=0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((16, 16))


def test_prime_tower_cycles():
    assert prime_tower(0) == 2
    assert prime_tower(1) == 3
    assert prime_tower(15) == prime_tower(0)


def test_emits_conformant_packet():
    core = ResidualCore(_cfg(), seed=0)
    p = core.step(_W())
    assert p.Ub.shape == (16, 4)
    assert p.Vb.shape == (4, 16)
    assert p.row_s_k.shape == (16,)
    assert p.col_s_k.shape == (16,)
    assert p.lat_s_k.shape == (4,)
    assert p.Lambda.shape == (4, 4)
    assert p.version == "1.0.0"
    assert len(p.packet_hash) == 64


def test_volume_preservation_holds():
    core = ResidualCore(_cfg(), seed=0)
    for _ in range(5):
        p = core.step(_W())
        assert p.volume_ok
        assert abs(np.log10(abs(p.volume) + 1e-300)) < 1e-9


def test_residual_scales_in_range():
    core = ResidualCore(_cfg(), seed=0)
    p = core.step(_W())
    for arr in (p.row_s_k, p.col_s_k, p.lat_s_k):
        assert arr.min() >= K_MIN
        assert arr.max() <= K_MAX


def test_determinism():
    p1 = ResidualCore(_cfg(), seed=0).step(_W())
    p2 = ResidualCore(_cfg(), seed=0).step(_W())
    assert packet_hash(p1) == packet_hash(p2)


def test_schedule_advances():
    core = ResidualCore(_cfg(), seed=0)
    p0 = core.step(_W())
    p1 = core.step(_W())
    assert p1.schedule_index == p0.schedule_index + 1
    assert p1.rank != p0.rank


def test_scar_diagonal_preserved():
    core = ResidualCore(_cfg(), seed=0)
    core.step(_W())
    assert np.allclose(np.diag(core.Lambda), 1.0)


def test_parity_hysteresis_holds_state():
    core = ResidualCore(_cfg(), seed=0)
    # F_res inside the hysteresis band → mu holds.
    p = core.step(_W(), mu=1, F_res=0.0, theta_hi=0.1, theta_lo=0.1)
    assert p.mu == 1
    p = core.step(_W(), mu=0, F_res=0.0, theta_hi=0.1, theta_lo=0.1)
    assert p.mu == 0


def test_parity_flips_on_crossing():
    core = ResidualCore(_cfg(), seed=0)
    p = core.step(_W(), mu=0, F_res=1.0, theta_hi=0.1, theta_lo=0.1)
    assert p.mu == 1
    p = core.step(_W(), mu=1, F_res=-1.0, theta_hi=0.1, theta_lo=0.1)
    assert p.mu == 0
