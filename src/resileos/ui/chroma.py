"""Belt chroma: orientation and compression for cheap visual variation.

The 5-mod Human Belt is 2 dyadic channels (black, white) plus 3
triadic channels (red, blue, yellow). A compact code stores those
five weights, an orientation scale, and a φ-step. Many palettes are
expanded from that code by rotating and permuting the belt and by
stepping hue and scale with φ. This does not re-render a frame for
each variation, does not call learn, does not write a scar, and does
not write Titanos.

Existing embed and codec outputs are unchanged unless a caller uses
these helpers. Video stays unavailable when no provider is configured;
this module does not add a provider.
"""
from __future__ import annotations

import itertools
import struct
import time
from typing import Any

import numpy as np

from resileos.ui.cascade_address import (
    BELT,
    DYADIC,
    ORIENTATION_SCALES,
    TRIADIC,
    orientation_scale,
)

# Channel names on the Human Belt, in order.
DYADIC_AXES = ("black", "white")
TRIADIC_AXES = ("red", "blue", "yellow")
BELT_AXES = DYADIC_AXES + TRIADIC_AXES
assert len(BELT_AXES) == BELT == DYADIC + TRIADIC

# Default hue steps used when expanding a code.
HUE_STEPS = 8
# Packed code: version, scale_level, hue_step, 5 float32 weights.
_CODE_FORMAT = "<BBB5f"
CODE_BYTES = struct.calcsize(_CODE_FORMAT)


def _phi() -> float:
    from resileos.substrate.suite_constants import PHI

    return float(PHI)


def normalize_chroma(chroma: Any = None) -> np.ndarray:
    """Five belt weights in [0, 1]. Missing values default to 0.5."""
    if chroma is None:
        values = np.full(BELT, 0.5, dtype=np.float64)
    else:
        values = np.asarray(list(chroma)[:BELT], dtype=np.float64)
        if values.size < BELT:
            values = np.pad(values, (0, BELT - values.size), constant_values=0.5)
    return np.clip(values, 0.0, 1.0)


def chroma_code(
    chroma: Any = None,
    *,
    orientation: str = "edge",
    hue_step: int = 0,
) -> dict[str, Any]:
    """Compact chroma / orientation code. No image is built."""
    control = orientation_scale(orientation)
    weights = normalize_chroma(chroma)
    step = int(hue_step) % HUE_STEPS
    return {
        "chroma": [float(x) for x in weights],
        "axes": list(BELT_AXES),
        "orientation": control["scale"],
        "scale_level": int(control["scale_level"]),
        "hue_step": step,
        "phi_weight": float(control["phi_weight"]),
        "belt": BELT,
    }


def pack_code(code: dict[str, Any]) -> bytes:
    """Fixed-size encoding of one chroma code."""
    weights = normalize_chroma(code.get("chroma"))
    level = int(code.get("scale_level") or 0) & 0xFF
    step = int(code.get("hue_step") or 0) % HUE_STEPS
    return struct.pack(_CODE_FORMAT, 1, level, step, *weights.astype(np.float32))


def unpack_code(data: bytes) -> dict[str, Any]:
    if len(data) != CODE_BYTES:
        raise ValueError("chroma code has the wrong length")
    version, level, step, *weights = struct.unpack(_CODE_FORMAT, data)
    if version != 1:
        raise ValueError("unknown chroma code version")
    names = ORIENTATION_SCALES
    orientation = names[level] if 0 <= level < len(names) else names[0]
    return chroma_code(weights, orientation=orientation, hue_step=step)


def _rotate_hue(triadic: np.ndarray, step: int) -> np.ndarray:
    """Rotate the RBY triple by 2π · frac(step · φ)."""
    angle = 2.0 * np.pi * ((step * _phi()) % 1.0)
    # Cycle the three triadic channels with a circular shift weighted
    # by the fractional turn, then a residual blend with the neighbour.
    shift = int(np.floor((step * _phi()) % 3.0))
    rotated = np.roll(triadic, shift)
    blend = angle / (2.0 * np.pi)
    neighbor = np.roll(rotated, 1)
    return (1.0 - blend) * rotated + blend * neighbor


def _palettes_from(code: dict[str, Any], *, include_scales: bool = False) -> list[dict[str, Any]]:
    base = normalize_chroma(code.get("chroma"))
    start_step = int(code.get("hue_step") or 0)
    levels = ORIENTATION_SCALES if include_scales else (code.get("orientation") or "edge",)
    palettes: list[dict[str, Any]] = []
    for orientation in levels:
        control = orientation_scale(orientation) if orientation in ORIENTATION_SCALES else orientation_scale("edge")
        for rot in range(BELT):
            rotated = np.roll(base, rot)
            for perm in itertools.permutations(range(TRIADIC)):
                for hue in range(HUE_STEPS):
                    dyadic = rotated[:DYADIC]
                    triadic = rotated[DYADIC:][list(perm)]
                    triadic = _rotate_hue(triadic, start_step + hue)
                    # Full strength at every frame: the orientation's φ
                    # address places the palette, it never dims it.
                    weights = np.concatenate([dyadic, triadic])
                    weights = np.clip(weights, 0.0, 1.0)
                    palettes.append(
                        {
                            "weights": [float(x) for x in weights],
                            "colors": _colors(weights),
                            "orientation": control["scale"],
                            "scale_level": int(control["scale_level"]),
                            "rotation": rot,
                            "triadic_perm": list(perm),
                            "hue_step": (start_step + hue) % HUE_STEPS,
                        }
                    )
    return palettes


def _colors(weights: np.ndarray) -> list[list[float]]:
    """Five RGB triples: black, white, red, blue, yellow, scaled by weight."""
    bases = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    return (bases * weights[:, None]).tolist()


def expand_variations(
    code: dict[str, Any] | bytes,
    *,
    include_scales: bool = False,
) -> list[dict[str, Any]]:
    """Expand a compact code into palettes. No frame is rendered."""
    if isinstance(code, (bytes, bytearray)):
        code = unpack_code(bytes(code))
    return _palettes_from(code, include_scales=include_scales)


def _ops_for_expand(n_rot: int, n_perm: int, n_hue: int, n_scale: int) -> int:
    """Counted arithmetic for one expand pass (no pixel loops)."""
    # roll of 5 + permute 3 + hue blend of 3 + scale of 5, per variation
    per = 5 + 3 + 3 + 5
    return int(n_rot * n_perm * n_hue * n_scale * per)


def _ops_for_naive_frames(n: int, height: int, width: int) -> int:
    """Counted writes to fill n RGB frames from a palette."""
    return int(n * height * width * 3)


def measure_variations(
    code: dict[str, Any] | None = None,
    *,
    shape: tuple[int, int] = (16, 16),
    include_scales: bool = False,
    repeats: int = 25,
) -> dict[str, Any]:
    """Compare compact expansion with storing naive frames. Real timings."""
    packed_in = chroma_code() if code is None else code
    packed = pack_code(packed_in)
    # Warm once so import costs are not in the timed loop.
    palettes = expand_variations(packed_in, include_scales=include_scales)
    n = len(palettes)
    height, width = shape
    start = time.perf_counter()
    for _ in range(repeats):
        expand_variations(packed_in, include_scales=include_scales)
    expand_s = (time.perf_counter() - start) / repeats
    # Naive: paint each variation onto a full frame.
    canvas = np.zeros((height, width, 3), dtype=np.float64)

    def _paint(palette: dict[str, Any]) -> np.ndarray:
        colors = np.asarray(palette["colors"], dtype=np.float64)
        frame = np.empty_like(canvas)
        # Tile the five colors across the frame. This is a full render.
        bands = np.array_split(frame, BELT, axis=1)
        for index, band in enumerate(bands):
            band[:] = colors[index % len(colors)]
        return frame

    start = time.perf_counter()
    for _ in range(max(1, repeats // 5)):
        frames = [_paint(item) for item in palettes]
    naive_s = (time.perf_counter() - start) / max(1, repeats // 5)
    frame_bytes = int(frames[0].nbytes) if palettes else 0
    n_scale = len(ORIENTATION_SCALES) if include_scales else 1
    return {
        "variations": n,
        "code_bytes": len(packed),
        "palette_bytes": n * BELT * 3 * 8,
        "naive_frame_bytes": n * frame_bytes,
        "ops_expand": _ops_for_expand(BELT, 6, HUE_STEPS, n_scale),
        "ops_naive_frames": _ops_for_naive_frames(n, height, width),
        "seconds_expand": expand_s,
        "seconds_naive_frames": naive_s,
        "shape": [height, width],
        "include_scales": include_scales,
        "repeats": repeats,
    }
