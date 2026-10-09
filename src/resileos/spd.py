"""
Positive-definiteness utility for the RES-601 §7 metric bridge.

The bridge itself remains locked until the three open items in RES-601 §7
are resolved (coordinates x, Re_ε and G derivations, definiteness check).
This module supplies the third item as a standalone utility so that when
the first two are available, the check is already in place.

Usage:
    assert_spd(M, name="g_ij")
    ok = is_spd(M)
"""
from __future__ import annotations

import torch


def is_spd(M: torch.Tensor, tol: float = 1e-8) -> bool:
    """
    Return True iff M is symmetric and has all strictly positive
    eigenvalues.

    Accepts 2D [D, D] or batched [B, D, D] real symmetric input.
    Non-square, non-symmetric, or rank-deficient input returns False.
    """
    if M.dim() not in (2, 3):
        raise ValueError(
            f"M must be [D, D] or [B, D, D], got {tuple(M.shape)}"
        )
    if M.shape[-1] != M.shape[-2]:
        return False
    if not torch.allclose(M, M.transpose(-1, -2), atol=tol):
        return False
    eigvals = torch.linalg.eigvalsh(M)
    return bool((eigvals > tol).all())


def assert_spd(M: torch.Tensor, name: str = "M", tol: float = 1e-8) -> None:
    """
    Raise ValueError if M is not symmetric positive definite.

    Reports the offending condition (shape, asymmetry, or minimum
    eigenvalue) so the caller knows which precondition failed.
    """
    if M.dim() not in (2, 3):
        raise ValueError(
            f"{name} must be [D, D] or [B, D, D], got {tuple(M.shape)}"
        )
    if M.shape[-1] != M.shape[-2]:
        raise ValueError(f"{name} is not square: {tuple(M.shape)}")

    asym = float((M - M.transpose(-1, -2)).abs().max().item())
    if asym > tol:
        raise ValueError(
            f"{name} is not symmetric (max asymmetry {asym:.3e} > tol {tol:.1e})"
        )

    eigvals = torch.linalg.eigvalsh(M)
    min_eig = float(eigvals.min().item())
    if min_eig <= tol:
        raise ValueError(
            f"{name} is not positive definite: "
            f"min eigenvalue {min_eig:.6e} ≤ tol {tol:.1e}"
        )


def min_eigenvalue(M: torch.Tensor) -> float:
    """
    Diagnostic helper: return the smallest eigenvalue of a symmetric M.
    Raises if M is not square or 2D/3D.
    """
    if M.dim() not in (2, 3):
        raise ValueError(f"M must be [D, D] or [B, D, D], got {tuple(M.shape)}")
    if M.shape[-1] != M.shape[-2]:
        raise ValueError(f"M is not square: {tuple(M.shape)}")
    return float(torch.linalg.eigvalsh(M).min().item())
