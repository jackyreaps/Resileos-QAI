"""Opt-in ternary front-end quantizer (RES-401-ternary)."""
from __future__ import annotations

import numpy as np
import pytest

# Prefer patch module during experiment; swap import when merged into training.py
from resileos.training_ternary_patch import (
    FrontEndEncoder,
    ste_sign,
    ste_ternary,
    ternary_to_bipolar,
)


def test_ste_ternary_values():
    x = np.array([-1.0, -0.01, 0.0, 0.01, 1.0], dtype=np.float32)
    y = ste_ternary(x, tau=0.05)
    assert set(np.unique(y).tolist()).issubset({-1.0, 0.0, 1.0})
    assert y[0] == -1.0 and y[-1] == 1.0
    assert y[2] == 0.0


def test_bipolar_default_unchanged_shape():
    enc = FrontEndEncoder(8, 8, 4, seed=0, mode="bipolar")
    W = np.random.randn(8, 8).astype(np.float32)
    out = enc.forward(W)
    assert out["Ub"].shape == (8, 4)
    assert out["Vb"].shape == (4, 8)
    assert set(np.unique(out["Ub"]).tolist()).issubset({-1.0, 1.0})


def test_ternary_mode_has_zeros_possible():
    enc = FrontEndEncoder(16, 16, 4, seed=1, mode="ternary", tau=0.5)
    W = np.random.randn(16, 16).astype(np.float32) * 0.1
    out = enc.forward(W)
    vals = set(np.unique(out["Ub"]).tolist()) | set(np.unique(out["Vb"]).tolist())
    assert vals.issubset({-1.0, 0.0, 1.0})


def test_ternary_to_bipolar_for_core():
    Ub = np.array([[-1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    Vb = np.array([[0.0, 1.0], [-1.0, 0.0]], dtype=np.float32)
    Ub2, Vb2 = ternary_to_bipolar(Ub, Vb)
    assert not np.any(Ub2 == 0.0)
    assert not np.any(Vb2 == 0.0)
    assert Ub2[0, 1] == 1.0


def test_factors_for_core_bipolar_path():
    enc = FrontEndEncoder(4, 4, 2, seed=2, mode="ternary", tau=0.05)
    W = np.eye(4, dtype=np.float32)
    out = enc.forward(W)
    Ub, Vb = enc.factors_for_core(out)
    assert set(np.unique(Ub).tolist()).issubset({-1.0, 1.0})
    assert set(np.unique(Vb).tolist()).issubset({-1.0, 1.0})
