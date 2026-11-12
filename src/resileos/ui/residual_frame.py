"""Inter-frame motion as a residual phase step.

Frames are gray in [0, 1]. The signal between them is the difference,
not a new sample:

    R = F_t - F_{t-1}

Direction is the spatial gradient of that residual. The suite scale

    s = MAGNETIC_PHASE / PHI

turns the mean gradient into a phase step (v_x, v_y). ``v`` is not a
pixel count and not an optical-flow vector. ``HEALING`` stays a recovery
scale on the oscillator. ``det J = 1`` stays the volume condition on the
cascade. Neither one is a factor of this vector.

The dual residual ``R* = -flip(R)`` is a check. Its energy is not a
second motion vector. No mirror helper in this repo already defined
that dual, so ``mirror_residual`` is this definition: negate a flip of
both spatial axes.

A prediction is the previous frame, a keyframe, or a bilinear upsample
of a draft. This module does not sample pixels, read a prompt, or call
a provider. The studio quantizer, not this file, packs ``R``.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.substrate import suite_constants

_PREDICTIONS = ("previous", "keyframe", "bilinear")


def as_gray(frame: Any) -> np.ndarray:
    """Gray in [0, 1]. Does not downsample and does not read a prompt."""
    array = np.asarray(frame, dtype=np.float64)
    if array.ndim == 3:
        rgb = array[..., :3]
        if rgb.size == 0:
            raise ValueError("frame is empty")
        if float(np.nanmax(rgb)) > 1.5:
            rgb = rgb / 255.0
        gray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    elif array.ndim == 2:
        gray = array
        if gray.size == 0:
            raise ValueError("frame is empty")
        if float(np.nanmax(gray)) > 1.5:
            gray = gray / 255.0
    else:
        raise ValueError(f"frame must be gray or color, got ndim {array.ndim}")
    if not np.isfinite(gray).all():
        raise ValueError("frame is not finite")
    return np.ascontiguousarray(np.clip(gray, 0.0, 1.0), dtype=np.float64)


def frame_residual(current: Any, previous: Any) -> np.ndarray:
    """R = F_t - F_{t-1}. The arguments are the frames, not an index step."""
    cur = np.asarray(current, dtype=np.float64)
    prev = np.asarray(previous, dtype=np.float64)
    if cur.ndim != 2 or prev.ndim != 2:
        raise ValueError("residual frames must be gray matrices")
    if cur.shape != prev.shape:
        raise ValueError(f"frame shapes differ: {cur.shape} and {prev.shape}")
    if cur.size == 0 or not np.isfinite(cur).all() or not np.isfinite(prev).all():
        raise ValueError("frames must be finite and non-empty")
    return cur - prev


def _residual_matrix(residual: Any) -> np.ndarray:
    array = np.asarray(residual, dtype=np.float64)
    if array.ndim != 2 or array.size == 0 or not np.isfinite(array).all():
        raise ValueError("residual must be a finite gray matrix")
    return array


def residual_gradient(residual: Any) -> tuple[np.ndarray, np.ndarray]:
    """(g_y, g_x) = ∇R on the residual grid.

    ``np.gradient`` is the spatial derivative. Its spacing is one cell of
    ``R``. That derivative is not the motion vector.
    """
    gradient_y, gradient_x = np.gradient(_residual_matrix(residual))
    return gradient_y, gradient_x


def mean_residual_gradient(residual: Any) -> tuple[float, float]:
    """(ḡ_x, ḡ_y), the mean of ∇R."""
    gradient_y, gradient_x = residual_gradient(residual)
    return float(np.mean(gradient_x)), float(np.mean(gradient_y))


def motion_scale() -> float:
    """s = MAGNETIC_PHASE / PHI, read from the suite constants each call."""
    phi = float(suite_constants.PHI)
    phase = float(suite_constants.MAGNETIC_PHASE)
    if not np.isfinite(phi) or not np.isfinite(phase) or phi == 0.0:
        raise ValueError("suite motion scale must be finite")
    return phase / phi


def motion_vector(residual: Any) -> dict[str, Any]:
    """(v_x, v_y) = s · (ḡ_x, ḡ_y), a phase step.

    Healing and det J are not factors. The result is not a pixel-index
    difference.
    """
    gbar_x, gbar_y = mean_residual_gradient(residual)
    scale = motion_scale()
    v_x = scale * gbar_x
    v_y = scale * gbar_y
    return {
        "v_x": float(v_x),
        "v_y": float(v_y),
        "magnitude": float(np.hypot(v_x, v_y)),
        "scale": float(scale),
        "gbar_x": float(gbar_x),
        "gbar_y": float(gbar_y),
        "unit": "phase_step",
    }


def mirror_residual(residual: Any) -> np.ndarray:
    """R* = -flip(R). Flip reverses both spatial axes."""
    return -np.flip(_residual_matrix(residual))


def mirror_energy(residual: Any) -> float:
    """⟨(R*)²⟩. A scalar check, not a motion vector."""
    dual = mirror_residual(residual)
    return float(np.mean(dual * dual))


def mirror_check(residual: Any) -> dict[str, Any]:
    """Mirror energy attached as evidence. No second vector."""
    return {
        "energy": mirror_energy(residual),
        "check": True,
        "second_motion_vector": False,
    }


def bilinear_upsample(image: Any, shape: tuple[int, int]) -> np.ndarray:
    """Bilinear resize of a gray draft. No provider and no learned weights."""
    src = np.asarray(image, dtype=np.float64)
    if src.ndim != 2 or src.size == 0:
        raise ValueError("draft must be a non-empty gray matrix")
    out_h, out_w = int(shape[0]), int(shape[1])
    if out_h < 1 or out_w < 1:
        raise ValueError("upsample shape must be positive")
    in_h, in_w = int(src.shape[0]), int(src.shape[1])
    if (in_h, in_w) == (out_h, out_w):
        return np.array(src, dtype=np.float64, copy=True)
    ys = np.array([0.0]) if out_h == 1 else np.linspace(0.0, in_h - 1, out_h)
    xs = np.array([0.0]) if out_w == 1 else np.linspace(0.0, in_w - 1, out_w)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    y1 = np.minimum(y0 + 1, in_h - 1)
    x1 = np.minimum(x0 + 1, in_w - 1)
    wy = (ys - y0)[:, None]
    wx = (xs - x0)[None, :]
    top = (1.0 - wx) * src[np.ix_(y0, x0)] + wx * src[np.ix_(y0, x1)]
    bottom = (1.0 - wx) * src[np.ix_(y1, x0)] + wx * src[np.ix_(y1, x1)]
    return np.ascontiguousarray((1.0 - wy) * top + wy * bottom, dtype=np.float64)


def predict_frame(
    current: Any,
    *,
    previous: Any = None,
    keyframe: Any = None,
    draft: Any = None,
    kind: str = "previous",
) -> tuple[np.ndarray, np.ndarray, str]:
    """Cheap prediction. Previous frame, keyframe, or bilinear draft.

    Returns gray ``(current, prediction, kind)`` on one shape. Nothing
    here calls a provider.
    """
    kind_name = str(kind or "previous")
    if kind_name not in _PREDICTIONS:
        raise ValueError("prediction must be previous, keyframe, or bilinear")
    current_gray = as_gray(current)
    if kind_name == "previous":
        if previous is None:
            raise ValueError("previous frame is required")
        prediction = as_gray(previous)
    elif kind_name == "keyframe":
        if keyframe is None:
            raise ValueError("keyframe is required")
        prediction = as_gray(keyframe)
    else:
        if draft is None:
            raise ValueError("draft is required")
        prediction = as_gray(draft)
    if prediction.shape != current_gray.shape:
        prediction = bilinear_upsample(prediction, current_gray.shape)
    return current_gray, prediction, kind_name


def apply_residual(prediction: Any, residual: Any) -> np.ndarray:
    """Candidate frame = prediction + decoded residual. Not a video frame."""
    pred = np.asarray(prediction, dtype=np.float64)
    residual_matrix = np.asarray(residual, dtype=np.float64)
    if pred.shape != residual_matrix.shape:
        raise ValueError(
            f"prediction and residual shapes differ: {pred.shape} and {residual_matrix.shape}"
        )
    if pred.ndim != 2 or not np.isfinite(pred).all() or not np.isfinite(residual_matrix).all():
        raise ValueError("prediction and residual must be finite gray matrices")
    return pred + residual_matrix


__all__ = [
    "apply_residual",
    "as_gray",
    "bilinear_upsample",
    "frame_residual",
    "mean_residual_gradient",
    "mirror_check",
    "mirror_energy",
    "mirror_residual",
    "motion_scale",
    "motion_vector",
    "predict_frame",
    "residual_gradient",
]
