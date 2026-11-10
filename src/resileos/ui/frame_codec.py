"""Lossy image and clip coding through ResidualCore.

ResidualCore factorizes a matrix into a stack of bipolar low-rank
layers (Ub @ Vb, scaled) and keeps the sum as ``last_reconstruction``.
That is a compressor for a matrix you already have. It is not a
generator: the control packet stores only layer 0's factors and no
per-layer scale, so a packet alone cannot rebuild the matrix, and
nothing in the core samples pixels from a prompt.

``encode_frame`` runs that stack. ``decode_frame`` sums the same
layers the core produced. The reconstruction error is
mean((W - decode)^2) on the grayscale projection, not on the
original pixel grid.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.core import CoreConfig, ResidualCore


def project_gray(arr: np.ndarray, m: int = 16, n: int = 16) -> np.ndarray:
    """Resize one frame to an m by n grayscale matrix in about [0, 1]."""
    a = np.asarray(arr)
    if a.ndim == 3:
        rgb = a[..., :3].astype(np.float64)
        if rgb.size and rgb.max() > 1.5:
            rgb = rgb / 255.0
        gray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    elif a.ndim == 2:
        gray = a.astype(np.float64)
        if gray.size and gray.max() > 1.5:
            gray = gray / 255.0
    else:
        flat = np.asarray(a, dtype=np.float64).ravel()
        gray = flat.reshape(1, -1) if flat.size else np.zeros((1, 1))
    if gray.size == 0:
        gray = np.zeros((1, 1), dtype=np.float64)
    h, w = gray.shape
    ys = np.clip(np.round(np.linspace(0, h - 1, m)).astype(int), 0, h - 1)
    xs = np.clip(np.round(np.linspace(0, w - 1, n)).astype(int), 0, w - 1)
    return gray[ys][:, xs].astype(np.float64)


def residual_bin(relative_mse: float) -> str:
    """Bin the core's relative residual energy. Not a luma/edge scaffold."""
    rel = float(relative_mse)
    if rel < 0.05:
        band = "low"
    elif rel < 0.5:
        band = "mid"
    else:
        band = "high"
    return f"rcore_{band}"


def encode_frame(
    arr: np.ndarray,
    *,
    m: int = 16,
    n: int = 16,
    rank: int = 4,
    n_layers: int = 4,
    seed: int = 0,
) -> dict[str, Any]:
    """Project one frame and compress it with ResidualCore.

    ``layers`` is the stack ``_factorize_residual_stack`` produced.
    ``mse`` compares the projection with ``core.last_reconstruction``.
    """
    matrix = project_gray(arr, m, n).astype(np.float32)
    rank_i = max(1, min(int(rank), m, n))
    core = ResidualCore(
        CoreConfig(m=m, n=n, r=rank_i, n_residual_layers=int(n_layers)),
        seed=int(seed),
    )
    stack, _ = core._factorize_residual_stack(matrix)
    packet = core.step(matrix)
    recon = np.asarray(core.last_reconstruction, dtype=np.float64)
    mse = float(np.mean((matrix - recon) ** 2))
    energy = float(np.mean(matrix ** 2))
    relative = mse / (energy + 1e-12)
    layers = [
        {
            "Ub": np.asarray(Ub, dtype=np.float64),
            "Vb": np.asarray(Vb, dtype=np.float64),
            "scale": float(scale),
        }
        for Ub, Vb, scale in stack
    ]
    return {
        "matrix": matrix,
        "reconstruction": recon,
        "layers": layers,
        "mse": mse,
        "relative_mse": relative,
        "residual_bin": residual_bin(relative),
        "packet_hash": packet.packet_hash,
        "shape": [m, n],
        "rank": rank_i,
        "n_layers": int(n_layers),
        "engine": "ResidualCore",
    }


def decode_frame(encoded: dict[str, Any]) -> np.ndarray:
    """Sum scale * Ub @ Vb for the layers encode_frame stored."""
    m, n = encoded["shape"]
    acc = np.zeros((int(m), int(n)), dtype=np.float64)
    for layer in encoded["layers"]:
        ub = np.asarray(layer["Ub"], dtype=np.float64)
        vb = np.asarray(layer["Vb"], dtype=np.float64)
        acc += float(layer["scale"]) * (ub @ vb)
    return acc


def codec_summary(encoded: dict[str, Any]) -> dict[str, Any]:
    """JSON-sized figures. Omits matrices and factors."""
    return {
        "engine": encoded["engine"],
        "mse": encoded["mse"],
        "relative_mse": encoded["relative_mse"],
        "residual_bin": encoded["residual_bin"],
        "packet_hash": encoded["packet_hash"],
        "shape": list(encoded["shape"]),
        "rank": encoded["rank"],
        "n_layers": encoded["n_layers"],
    }


def encode_clip(frames: np.ndarray, **kwargs: Any) -> dict[str, Any]:
    """Encode up to four frames. Error is the mean of the frame MSEs."""
    f = np.asarray(frames)
    if f.ndim == 2:
        f = f[None, ...]
    elif f.ndim == 3 and f.shape[-1] in (1, 3, 4):
        f = f[None, ...]
    elif f.ndim == 3:
        f = f[..., None]
    if f.ndim != 4:
        f = np.zeros((1, 8, 8, 1), dtype=np.float64)
    n = min(int(f.shape[0]), 4)
    codes = [encode_frame(f[i], **kwargs) for i in range(n)]
    rel = float(np.mean([c["relative_mse"] for c in codes])) if codes else 0.0
    mse = float(np.mean([c["mse"] for c in codes])) if codes else 0.0
    return {
        "frames_encoded": len(codes),
        "mse": mse,
        "relative_mse": rel,
        "residual_bin": residual_bin(rel),
        "frames": codes,
        "engine": "ResidualCore",
    }
