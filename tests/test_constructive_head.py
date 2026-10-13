"""
Tests for the constructive head (RES-308).

Verify shape, determinism, mode dispatch. Do not assert predictive
accuracy: the head is constructive (not trained) and there is no
(x_t, x_{t+1}) dataset yet.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.constructive import ConstructiveHead


DIM = 64
M = 8
N = 8
R = 4


def _packet(lambda_prev_factor: float = 1.0):
    rng = np.random.default_rng(0)
    Ub = rng.choice([-1.0, 1.0], size=(M, R)).astype(np.float32)
    Vb = rng.choice([-1.0, 1.0], size=(R, N)).astype(np.float32)
    Lam = (lambda_prev_factor * np.eye(R, dtype=np.float32)
           + 0.1 * rng.standard_normal((R, R)).astype(np.float32))
    return {"Ub": Ub, "Vb": Vb, "Lambda": Lam}


def _lambda_prev():
    return np.eye(R, dtype=np.float32)


def _theta():
    rng = np.random.default_rng(1)
    t = rng.standard_normal(R)
    return t - t.mean()


def test_trend_shape():
    h = ConstructiveHead(DIM, M, N, mode="trend")
    d = h.forward(np.zeros(DIM), _packet(), lambda_prev=_lambda_prev())
    assert d.shape == (DIM,)
    assert d.dtype == np.float64


def test_phase_shape():
    h = ConstructiveHead(DIM, M, N, mode="phase")
    d = h.forward(np.zeros(DIM), _packet(), theta=_theta())
    assert d.shape == (DIM,)


def test_both_shape():
    h = ConstructiveHead(DIM, M, N, mode="both")
    d = h.forward(np.zeros(DIM), _packet(),
                  lambda_prev=_lambda_prev(), theta=_theta())
    assert d.shape == (DIM,)


def test_trend_zero_when_no_prev():
    h = ConstructiveHead(DIM, M, N, mode="trend")
    d = h.forward(np.zeros(DIM), _packet(), lambda_prev=None)
    assert np.allclose(d, 0.0)


def test_phase_zero_when_no_theta():
    h = ConstructiveHead(DIM, M, N, mode="phase")
    d = h.forward(np.zeros(DIM), _packet(), theta=None)
    assert np.allclose(d, 0.0)


def test_trend_deterministic():
    h = ConstructiveHead(DIM, M, N, mode="trend")
    p = _packet()
    lp = _lambda_prev()
    d1 = h.forward(np.zeros(DIM), p, lambda_prev=lp)
    d2 = h.forward(np.zeros(DIM), p, lambda_prev=lp)
    assert np.array_equal(d1, d2)


def test_phase_deterministic():
    h = ConstructiveHead(DIM, M, N, mode="phase")
    p = _packet()
    th = _theta()
    d1 = h.forward(np.zeros(DIM), p, theta=th)
    d2 = h.forward(np.zeros(DIM), p, theta=th)
    assert np.array_equal(d1, d2)


def test_trend_nonzero_on_real_change():
    h = ConstructiveHead(DIM, M, N, mode="trend")
    d = h.forward(np.zeros(DIM), _packet(lambda_prev_factor=1.0),
                  lambda_prev=_lambda_prev())
    assert np.linalg.norm(d) > 0.0


def test_phase_nonzero_on_real_theta():
    h = ConstructiveHead(DIM, M, N, mode="phase")
    d = h.forward(np.zeros(DIM), _packet(), theta=_theta())
    assert np.linalg.norm(d) > 0.0


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown mode"):
        ConstructiveHead(DIM, M, N, mode="nonsense")


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="m\\*n"):
        ConstructiveHead(16, 8, 8)


def test_theta_length_mismatch_raises():
    h = ConstructiveHead(DIM, M, N, mode="phase")
    with pytest.raises(ValueError, match="theta length"):
        h.forward(np.zeros(DIM), _packet(), theta=np.zeros(R + 1))


def test_lambda_prev_shape_mismatch_raises():
    h = ConstructiveHead(DIM, M, N, mode="trend")
    with pytest.raises(ValueError, match="lambda_prev shape"):
        h.forward(np.zeros(DIM), _packet(),
                  lambda_prev=np.zeros((R + 1, R + 1)))


def test_both_equals_sum_of_parts():
    h_t = ConstructiveHead(DIM, M, N, mode="trend")
    h_p = ConstructiveHead(DIM, M, N, mode="phase")
    h_b = ConstructiveHead(DIM, M, N, mode="both")
    p = _packet()
    lp = _lambda_prev()
    th = _theta()
    d_t = h_t.forward(np.zeros(DIM), p, lambda_prev=lp)
    d_p = h_p.forward(np.zeros(DIM), p, theta=th)
    d_b = h_b.forward(np.zeros(DIM), p, lambda_prev=lp, theta=th)
    assert np.allclose(d_b, d_t + d_p)


def test_scale_multiplies_output():
    p = _packet()
    th = _theta()
    h1 = ConstructiveHead(DIM, M, N, mode="phase", scale=1.0)
    h2 = ConstructiveHead(DIM, M, N, mode="phase", scale=2.5)
    d1 = h1.forward(np.zeros(DIM), p, theta=th)
    d2 = h2.forward(np.zeros(DIM), p, theta=th)
    assert np.allclose(d2, 2.5 * d1)


def test_describe_reports_no_quantum_capability():
    h = ConstructiveHead(DIM, M, N, mode="both")
    d = h.describe()
    assert d["quantum_capability"] is False
    assert d["quantum_shaped_math"] is True
    assert d["trained"] is False
