"""Toy class-conditional PCA prior over residual codes.

Fits a Gaussian in a PCA subspace of the code vectors (bipolar factors as
±1, plus the stored scales), per digit class. Sampling snaps the factor
coordinates back to ±1 and decodes with the studio codec.

This is not a generative model. It does not see pixels at sample time, and
it does not see text. Callers should label every sample as a toy.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from studio.codec import decode


def code_vector(packet: dict[str, Any]) -> np.ndarray:
    parts: list[np.ndarray] = []
    for layer in packet["layers"]:
        parts.append(np.asarray(layer["Ub"], dtype=np.float64).ravel())
        parts.append(np.asarray(layer["Vb"], dtype=np.float64).ravel())
        scale = np.atleast_1d(np.asarray(layer["scale"], dtype=np.float64)).ravel()
        parts.append(scale)
    return np.concatenate(parts)


def _layout(template: dict[str, Any]) -> list[tuple[str, tuple[int, ...]]]:
    slots: list[tuple[str, tuple[int, ...]]] = []
    for layer in template["layers"]:
        slots.append(("Ub", tuple(np.asarray(layer["Ub"]).shape)))
        slots.append(("Vb", tuple(np.asarray(layer["Vb"]).shape)))
        scale = np.atleast_1d(np.asarray(layer["scale"], dtype=np.float64))
        slots.append(("scale", (int(scale.size),)))
    return slots


def packet_from_code(template: dict[str, Any], code: np.ndarray) -> dict[str, Any]:
    """Snap factor coordinates to ±1 and copy scales into a new packet."""
    slots = _layout(template)
    expected = sum(int(np.prod(shape)) for _, shape in slots)
    vector = np.asarray(code, dtype=np.float64).ravel()
    if vector.size != expected:
        raise ValueError(f"code length {vector.size} != template length {expected}")
    layers: list[dict[str, Any]] = []
    cursor = 0
    current: dict[str, Any] = {}
    for kind, shape in slots:
        width = int(np.prod(shape))
        chunk = vector[cursor : cursor + width]
        cursor += width
        if kind == "scale":
            if template["scale_mode"] == "layer":
                current["scale"] = float(chunk[0])
            else:
                current["scale"] = [float(v) for v in chunk]
            layers.append(current)
            current = {}
        else:
            signed = np.sign(chunk)
            signed[signed == 0] = 1.0
            current[kind] = signed.astype(np.float32).reshape(shape)
    packet = {
        "version": template["version"],
        "shape": list(template["shape"]),
        "rank": int(template["rank"]),
        "n_layers": int(template["n_layers"]),
        "scale_mode": template["scale_mode"],
        "basis": "toy-prior",
        "layers": layers,
        "logical_bits": int(template["logical_bits"]),
    }
    return packet


def fit_class_conditional(
    codes: np.ndarray,
    labels: np.ndarray,
    *,
    n_components: int = 16,
) -> dict[str, Any]:
    """PCA on all codes, then a diagonal Gaussian of the scores per class."""
    data = np.asarray(codes, dtype=np.float64)
    y = np.asarray(labels)
    if data.ndim != 2:
        raise ValueError(f"codes must be (N, D), got {data.shape}")
    if y.shape[0] != data.shape[0]:
        raise ValueError("labels and codes length differ")
    mean = data.mean(axis=0)
    centered = data - mean
    # Economy SVD. Components are rows of Vt.
    _u, singular, vt = np.linalg.svd(centered, full_matrices=False)
    rank = int(min(n_components, vt.shape[0], max(data.shape[0] - 1, 1)))
    components = vt[:rank]
    scores = centered @ components.T
    variance = (singular[:rank] ** 2) / max(data.shape[0] - 1, 1)
    total = float(np.sum(singular**2) / max(data.shape[0] - 1, 1))
    explained = float(np.sum(variance) / total) if total > 0 else 0.0
    classes: dict[str, dict[str, Any]] = {}
    for label in sorted(set(int(v) for v in y.tolist())):
        block = scores[y == label]
        classes[str(label)] = {
            "count": int(block.shape[0]),
            "mean": block.mean(axis=0),
            "std": block.std(axis=0, ddof=1) if block.shape[0] > 1 else np.zeros(rank),
        }
    return {
        "mean": mean,
        "components": components,
        "explained_variance_ratio": explained,
        "n_components": rank,
        "classes": classes,
        "code_dim": int(data.shape[1]),
        "n_codes": int(data.shape[0]),
    }


def sample_code(model: dict[str, Any], label: int, rng: np.random.Generator) -> np.ndarray:
    spec = model["classes"][str(int(label))]
    mean = np.asarray(spec["mean"], dtype=np.float64)
    std = np.asarray(spec["std"], dtype=np.float64)
    draw = rng.normal(mean, std)
    return np.asarray(model["mean"], dtype=np.float64) + draw @ np.asarray(model["components"])


def majority_code(codes: np.ndarray) -> np.ndarray:
    """Coordinate-wise mean. Factor slots are snapped to a majority ±1 later."""
    return np.asarray(codes, dtype=np.float64).mean(axis=0)


def decode_code(template: dict[str, Any], code: np.ndarray) -> np.ndarray:
    return decode(packet_from_code(template, code))
