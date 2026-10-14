"""Tests for the monitor surface and the ε composition."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import CoreConfig, ResidualCore
from resileos.monitors import (
    MonitorBundle, epsilon_from_monitors, pack_extra_monitors,
)


def _core(**kwargs):
    return ResidualCore(CoreConfig(m=8, n=8, r=4, **kwargs), seed=0)


def _step(core, seed=0):
    W = np.random.default_rng(seed).standard_normal((8, 8))
    return core.step(W, mu=0, F_res=0.1, DeltaS=0.5)


# ── core.monitors() ─────────────────────────────────────────────────────
def test_monitors_none_before_step():
    core = _core()
    assert core.monitors() is None


def test_monitors_returns_bundle_after_step():
    core = _core()
    _step(core)
    bundle = core.monitors()
    assert isinstance(bundle, MonitorBundle)


def test_monitors_matches_packet_fields():
    core = _core()
    packet = _step(core)
    bundle = core.monitors()
    assert np.isclose(bundle.F_res, packet.F_res)
    assert np.isclose(bundle.DeltaS, packet.DeltaS)
    assert bundle.mu == packet.mu
    assert np.isclose(bundle.volume, packet.volume)
    assert bundle.rank == packet.rank
    assert bundle.schedule_index == packet.schedule_index


def test_monitors_lambda_energy_from_scar():
    core = _core()
    packet = _step(core)
    bundle = core.monitors()
    expected = float(np.linalg.norm(packet.Lambda))
    assert np.isclose(bundle.lambda_energy, expected)


def test_monitors_anisotropy_in_conservative_mode():
    core = _core()  # non_conservative=False
    _step(core)
    bundle = core.monitors()
    assert np.isclose(bundle.anisotropy, 1.0, atol=1e-9)


def test_monitors_anisotropy_in_non_conservative_mode():
    core = _core()
    core = ResidualCore(CoreConfig(m=8, n=8, r=4), seed=0,
                        non_conservative=True)
    for i in range(5):
        _step(core, seed=i)
    bundle = core.monitors()
    assert bundle.anisotropy >= 1.0


def test_monitors_bundle_is_frozen():
    """MonitorBundle is a frozen dataclass; no in-place edits."""
    core = _core()
    _step(core)
    bundle = core.monitors()
    with pytest.raises(Exception):
        bundle.F_res = 99.0


# ── bundle introspection ────────────────────────────────────────────────
def test_bundle_as_array_shape():
    core = _core()
    _step(core)
    arr = core.monitors().as_array()
    assert arr.shape == (8,)
    assert arr.dtype == np.float64


def test_bundle_to_dict_keys():
    core = _core()
    _step(core)
    d = core.monitors().to_dict()
    for k in ("F_res", "DeltaS", "mu", "lambda_energy",
              "anisotropy", "volume", "rank", "schedule_index"):
        assert k in d


# ── epsilon_from_monitors ───────────────────────────────────────────────
def _bundle(F_res=0.0, DeltaS=0.0, mu=0, lambda_energy=0.0,
            anisotropy=1.0, volume=1.0, rank=1, schedule_index=0):
    return MonitorBundle(
        F_res=F_res, DeltaS=DeltaS, mu=mu, lambda_energy=lambda_energy,
        anisotropy=anisotropy, volume=volume, rank=rank,
        schedule_index=schedule_index,
    )


def test_epsilon_zero_chaos_returns_floor():
    b = _bundle(F_res=0.0, DeltaS=0.0, anisotropy=1.0)
    eps = epsilon_from_monitors(b)
    assert eps >= 1e-3


def test_epsilon_increases_with_f_res():
    b1 = _bundle(F_res=0.1)
    b2 = _bundle(F_res=1.0)
    assert epsilon_from_monitors(b2) > epsilon_from_monitors(b1)


def test_epsilon_increases_with_anisotropy():
    b1 = _bundle(anisotropy=1.0)
    b2 = _bundle(anisotropy=3.0)
    assert epsilon_from_monitors(b2) > epsilon_from_monitors(b1)


def test_epsilon_ignores_anisotropy_below_one():
    b1 = _bundle(anisotropy=0.5)
    b2 = _bundle(anisotropy=1.0)
    assert np.isclose(epsilon_from_monitors(b1),
                      epsilon_from_monitors(b2))


def test_epsilon_monotone_in_delta_s():
    b1 = _bundle(DeltaS=0.1)
    b2 = _bundle(DeltaS=1.0)
    assert epsilon_from_monitors(b2) > epsilon_from_monitors(b1)


def test_epsilon_always_positive():
    for f in (-1.0, -0.5, 0.0, 0.5, 1.0):
        for d in (-1.0, 0.0, 1.0):
            eps = epsilon_from_monitors(_bundle(F_res=f, DeltaS=d))
            assert eps >= 1e-3


def test_epsilon_floor_customizable():
    b = _bundle(F_res=0.0, DeltaS=0.0)
    eps = epsilon_from_monitors(b, alpha_floor=0.01)
    assert eps == 0.01


# ── pack_extra_monitors ─────────────────────────────────────────────────
def test_pack_extra_monitors_base():
    b = _bundle()
    arr = pack_extra_monitors(b)
    assert arr.shape == (3,)
    assert arr[0] == b.lambda_energy
    assert arr[1] == b.anisotropy


def test_pack_extra_monitors_with_csi():
    b = _bundle()
    arr = pack_extra_monitors(b, csi=0.7)
    assert arr.shape == (4,)
    assert arr[3] == 0.7


def test_pack_extra_monitors_with_csi_and_R():
    b = _bundle()
    arr = pack_extra_monitors(b, csi=0.7, R=0.9)
    assert arr.shape == (5,)
    assert arr[3] == 0.7
    assert arr[4] == 0.9


def test_pack_extra_monitors_rank_normalized():
    b = _bundle(rank=50)
    arr = pack_extra_monitors(b)
    assert np.isclose(arr[2], 0.5)
