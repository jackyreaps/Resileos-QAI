"""Positive-definiteness helpers for metric tensors (RES-601 §7 item 3)."""
from __future__ import annotations

import numpy as np


def assert_spd(M, name: str = "M", tol: float = 1e-10) -> float:
    A = np.asarray(M, dtype=np.float64)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"{name}: expected square matrix, got shape {A.shape}")
    if not np.allclose(A, A.T, atol=tol):
        raise ValueError(
            f"{name}: not symmetric (max |A-A.T| = {np.max(np.abs(A - A.T))})"
        )
    w = np.linalg.eigvalsh(0.5 * (A + A.T))
    min_eig = float(w.min())
    if min_eig <= tol:
        raise ValueError(
            f"{name}: not positive-definite (min eigenvalue = {min_eig})"
        )
    return min_eig


def is_spd(M, tol: float = 1e-10) -> bool:
    try:
        assert_spd(M, tol=tol)
        return True
    except ValueError:
        return False


def isotropic_metric(dim: int, re_eps: float = 0.0) -> np.ndarray:
    if re_eps <= -1.0:
        raise ValueError("Re_ε must be > -1 for conformal positivity")
    return (1.0 / (1.0 + re_eps)) * np.eye(dim, dtype=np.float64)
