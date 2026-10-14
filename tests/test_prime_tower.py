"""Tests for the prime tower (X-Files 06-prime-tower-hypothesis.md)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.hierarchy.prime_tower import PrimeTower, cipolla


def _tower(**kw):
    base = dict(max_level=32)
    base.update(kw)
    return PrimeTower(**base)


# ── construction ────────────────────────────────────────────────────────
def test_tower_rejects_max_level_below_2():
    with pytest.raises(ValueError, match="max_level"):
        PrimeTower(max_level=1)


def test_tower_coerces_max_level():
    t = PrimeTower(max_level="16")
    assert t.max_level == 16


# ── primes ──────────────────────────────────────────────────────────────
def test_prime_first_ten():
    t = _tower()
    expected = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    for i, p in enumerate(expected, start=1):
        assert t.prime(i) == p


def test_prime_rejects_out_of_range():
    t = _tower(max_level=10)
    with pytest.raises(ValueError, match="out of range"):
        t.prime(11)


def test_prime_rejects_zero():
    t = _tower()
    with pytest.raises(ValueError, match="out of range"):
        t.prime(0)


def test_primes_property():
    t = _tower(max_level=5)
    assert t.primes == [2, 3, 5, 7, 11]


# ── Cipolla ─────────────────────────────────────────────────────────────
def test_cipolla_rejects_below_1():
    with pytest.raises(ValueError, match="k must be"):
        cipolla(0)


def test_cipolla_positive():
    for k in range(3, 20):
        assert cipolla(k) > 0.0


def test_cipolla_grows():
    assert cipolla(10) < cipolla(20) < cipolla(50)


# ── S_k ─────────────────────────────────────────────────────────────────
def test_S_1_and_2_are_1():
    t = _tower()
    assert t.S(1) == pytest.approx(1.0)
    assert t.S(2) == pytest.approx(1.0)


def test_S_k_positive():
    t = _tower()
    for k in range(3, 16):
        assert t.S(k) > 0.0


def test_S_rejects_out_of_range():
    t = _tower(max_level=10)
    with pytest.raises(ValueError, match="out of range"):
        t.S(11)


# ── T(n) ────────────────────────────────────────────────────────────────
def test_T_2_equals_S_2():
    t = _tower()
    assert t.T(2) == pytest.approx(t.S(2))


def test_T_recurrence():
    t = _tower()
    for n in range(3, 12):
        expected = t.S(n) / t.T(n - 1)
        assert t.T(n) == pytest.approx(expected)


def test_T_rejects_below_2():
    t = _tower()
    with pytest.raises(ValueError, match="out of range"):
        t.T(1)


def test_T_rejects_above_max():
    t = _tower(max_level=8)
    with pytest.raises(ValueError, match="out of range"):
        t.T(9)


def test_T_product_equals_S():
    """The tower's intrinsic quantity: T(n) * T(n-1) = S_n."""
    t = _tower()
    for n in range(3, 12):
        product = t.T(n) * t.T(n - 1)
        assert product == pytest.approx(t.S(n), rel=1e-9)


# ── branch ──────────────────────────────────────────────────────────────
def test_branch_even():
    assert PrimeTower.branch(2) == "even"
    assert PrimeTower.branch(4) == "even"


def test_branch_odd():
    assert PrimeTower.branch(3) == "odd"
    assert PrimeTower.branch(5) == "odd"


def test_branch_rejects_below_2():
    with pytest.raises(ValueError, match="n must be"):
        PrimeTower.branch(1)


def test_is_forbidden_odd():
    t = _tower()
    assert t.is_forbidden(3)
    assert t.is_forbidden(5)


def test_is_forbidden_even_false():
    t = _tower()
    assert not t.is_forbidden(2)
    assert not t.is_forbidden(4)


# ── Nyquist bound ───────────────────────────────────────────────────────
def test_n_usable_dim_64():
    """At dim=64, Nyquist is 32. Largest prime < 32 is 31 (p_11).
    Levels 2..11 -> 10 usable."""
    t = _tower(max_level=32)
    assert t.n_usable(64) == 10


def test_n_usable_dim_512():
    """At dim=512, Nyquist is 256. Largest prime < 256 is 251 (p_54).
    Levels 2..54 -> 53 usable."""
    t = _tower(max_level=64)
    assert t.n_usable(512) == 53


def test_n_usable_rejects_small_dim():
    t = _tower()
    with pytest.raises(ValueError, match="dim must be"):
        t.n_usable(2)


def test_max_usable_level():
    t = _tower(max_level=32)
    assert t.max_usable_level(64) == 11


# ── snapshot ────────────────────────────────────────────────────────────
def test_snapshot_keys():
    t = _tower(max_level=8)
    s = t.snapshot()
    for k in ("max_level", "primes", "S", "T"):
        assert k in s


def test_repr():
    t = _tower(max_level=16)
    assert "PrimeTower" in repr(t)
    assert "max_level=16" in repr(t)
