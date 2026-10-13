"""
Positive-definiteness utility for the RES-601 §7 metric bridge.

The bridge itself remains locked until the open items in RES-601 §7 are
resolved. This module supplies the definiteness precondition as a
standalone utility so that when the metric exists, the check is ready.
"""
from __future__ import annotations

import numpy as np


def assert_spd(M, name: str = "M", tol: float = 1e-10) -> float:
    """
    Raise ValueError if M is not symmetric positive definite.
    Returns the minimum eigenvalue on success.

    Accepts [D, D] or [B, D, D] real input.
    """
    A = np.asarray(M, dtype=np.float64)
    if A.ndim not in (2, 3):
        raise ValueError(
            f"{name}: expected [D, D] or [B, D, D], got shape {A.shape}")
    if A.shape[-1] != A.shape[-2]:
        raise ValueError(f"{name}: not square, got shape {A.shape}")

    asym = float(np.max(np.abs(A - np.swapaxes(A, -1, -2))))
    if asym > tol:
        raise ValueError(
            f"{name}: not symmetric (max asymmetry {asym:.3e} > tol {tol:.1e})")

    w = np.linalg.eigvalsh(0.5 * (A + np.swapaxes(A, -1, -2)))
    min_eig = float(w.min())
    if min_eig <= tol:
        raise ValueError(
            f"{name}: not positive-definite (min eigenvalue {min_eig:.6e})")
    return min_eig


def is_spd(M, tol: float = 1e-10) -> bool:
    try:
        assert_spd(M, tol=tol)
        return True
    except ValueError:
        return False


def min_eigenvalue(M) -> float:
    """
    Smallest eigenvalue of a symmetric matrix. Raises if M is not
    square. Does not require positive definiteness.
    """
    A = np.asarray(M, dtype=np.float64)
    if A.ndim not in (2, 3):
        raise ValueError(
            f"M must be [D, D] or [B, D, D], got shape {A.shape}")
    if A.shape[-1] != A.shape[-2]:
        raise ValueError(f"M is not square: {A.shape}")
    return float(np.linalg.eigvalsh(0.5 * (A + np.swapaxes(A, -1, -2))).min())


def isotropic_metric(dim: int, re_eps: float = 0.0) -> np.ndarray:
    """
    SPECIFICATION COMPLIANCE STATUS: CONFORMAL PLACEHOLDER.

    g = I / (1 + Re_ε). This is not the RES-601 §7 bridge; it is a
    positive-definite placeholder with a single scalar parameter.
    """
    if re_eps <= -1.0:
        raise ValueError("Re_ε must be > -1 for conformal positivity")
    return (1.0 / (1.0 + re_eps)) * np.eye(dim, dtype=np.float64)


__all__ = ["assert_spd", "is_spd", "min_eigenvalue", "isotropic_metric"]
