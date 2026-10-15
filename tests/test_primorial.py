"""Tests for primorial carriers (RES-312 extension)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.hierarchy.primorial import (
    n_usable_primorials,
    primorial,
    primorial_carrier,
)


def test_primorial_small():
    assert primorial(0) == 1
    assert primorial(1) == 2
    assert primorial(2) == 6
    assert primorial(3) == 30
    assert primorial(4) == 210
    assert primorial(5) == 2310


def test_primorial_rejects_negative():
    with pytest.raises(ValueError):
        primorial(-1)


def test_n_usable_dim_64():
    # P_k < 32: 2, 6, 30 -> k = 3
    assert n_usable_primorials(64) == 3


def test_n_usable_dim_512():
    # P_k < 256: 2, 6, 30, 210 -> k = 4
    assert n_usable_primorials(512) == 4


def test_n_usable_dim_4096():
    # P_k < 2048: 2, 6, 30, 210 fit; 2310 >= 2048 does not -> k = 4
    assert n_usable_primorials(4096) == 4


def test_n_usable_rejects_small_dim():
    with pytest.raises(ValueError):
        n_usable_primorials(2)


def test_carrier_unit_norm():
    c = primorial_carrier(2, 512)
    assert abs(float(np.linalg.norm(c)) - 1.0) < 1e-9


def test_carrier_rejects_nyquist():
    with pytest.raises(ValueError, match="Nyquist"):
        primorial_carrier(5, 64)


def test_carrier_deterministic():
    a = primorial_carrier(3, 512)
    b = primorial_carrier(3, 512)
    assert np.allclose(a, b)


def test_carrier_distinct_levels():
    c1 = primorial_carrier(1, 512)
    c2 = primorial_carrier(2, 512)
    c3 = primorial_carrier(3, 512)
    assert not np.allclose(c1, c2)
    assert not np.allclose(c2, c3)
    for a, b in [(c1, c2), (c2, c3), (c1, c3)]:
        ip = abs(float(np.real(np.vdot(a, b))))
        assert ip < 0.2
