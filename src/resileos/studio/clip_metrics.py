"""Extra deterministic check metrics for a residual clip.

Two measurements over the frames a clip sequence decodes to. They are
recorded next to the verify result. They do not change it: the clip
verify gate in ``sequence_stage._judge`` is unchanged, and nothing here
is a replacement for that gate.

motion_phase_coherence
    Each frame transition t gets an integer translation (dy, dx) from
    phase correlation (the peak of the inverse normalised cross-power
    spectrum). Its angle is θ_t = atan2(dy, dx).
    R = |mean_t exp(i θ_t)| over transitions that moved (the Kuramoto
    order parameter of those angles, same formula as
    ``KuramotoField.order_parameter``). R = 1 means every transition
    moved the same way; R near 0 means directions cancel. With fewer than
    two moving transitions R is None. No oscillator is simulated.

residual_betti
    For each transition, the residual F_t - F_{t-1} is thresholded at
    ``max(floor, frac * max|R|)``. b0 is the number of 4-connected
    components of the active cells. b1 is the number of 8-connected
    inactive regions that do not touch the border (holes). These are the
    Betti numbers of the active region under the standard 4/8 digital
    topology pairing. This is a per-frame count, not persistent homology.

Pure numpy. No learn, no scar matrix, no Titanos, no provider.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from resileos.ui.residual_frame import frame_residual

METRICS_VERSION = "clip-metrics/1"
MOTION_FLOOR = 1e-9
ACTIVE_FLOOR = 1e-3
ACTIVE_FRAC = 0.25

_N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_N8 = _N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def order_parameter(angles: Any) -> Optional[float]:
    """R = |mean exp(iθ)|. None for an empty set."""
    theta = np.asarray(angles, dtype=np.float64).ravel()
    if theta.size == 0:
        return None
    return float(np.abs(np.mean(np.exp(1j * theta))))


def phase_shift(previous: Any, current: Any) -> tuple[int, int, float]:
    """(dy, dx, peak) from phase correlation of two frames.

    The normalised cross-power spectrum of the two frames is inverted;
    its peak is the integer translation from ``previous`` to ``current``.
    Shifts wrap to the signed range. ``peak`` is the correlation height.
    """
    a = np.asarray(previous, dtype=np.float64)
    b = np.asarray(current, dtype=np.float64)
    fa = np.fft.fft2(a - a.mean())
    fb = np.fft.fft2(b - b.mean())
    cross = fb * np.conj(fa)
    mag = np.abs(cross)
    if not np.any(mag > MOTION_FLOOR):
        return 0, 0, 0.0
    cross = np.where(mag > MOTION_FLOOR, cross / np.maximum(mag, MOTION_FLOOR), 0.0)
    corr = np.real(np.fft.ifft2(cross))
    py, px = np.unravel_index(int(np.argmax(corr)), corr.shape)
    h, w = corr.shape
    dy = int(py) - h if py > h // 2 else int(py)
    dx = int(px) - w if px > w // 2 else int(px)
    return dy, dx, float(corr[py, px])


def motion_phase_coherence(frames: list[Any]) -> dict[str, Any]:
    angles: list[float] = []
    shifts: list[list[int]] = []
    for index in range(1, len(frames)):
        residual = frame_residual(frames[index], frames[index - 1])
        if float(np.max(np.abs(residual))) <= ACTIVE_FLOOR:
            shifts.append([0, 0])
            continue
        dy, dx, _peak = phase_shift(frames[index - 1], frames[index])
        shifts.append([dy, dx])
        if dy or dx:
            angles.append(float(np.arctan2(dy, dx)))
    value = order_parameter(angles) if len(angles) >= 2 else None
    return {
        "R": value,
        "moving_transitions": len(angles),
        "transitions": max(0, len(frames) - 1),
        "shifts": shifts,
    }


def _components(mask: np.ndarray, neighbours: tuple) -> list[list[tuple[int, int]]]:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    groups: list[list[tuple[int, int]]] = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            cells = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy, dx in neighbours:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            groups.append(cells)
    return groups


def betti_numbers(mask: Any) -> tuple[int, int]:
    """(b0, b1) of a binary grid: 4-connected foreground, 8-connected holes."""
    grid = np.asarray(mask, dtype=bool)
    if grid.ndim != 2:
        raise ValueError("mask must be 2-D")
    b0 = len(_components(grid, _N4))
    h, w = grid.shape
    holes = 0
    for cells in _components(~grid, _N8):
        if not any(y in (0, h - 1) or x in (0, w - 1) for y, x in cells):
            holes += 1
    return b0, holes


def residual_mask(residual: Any, *, floor: float = ACTIVE_FLOOR, frac: float = ACTIVE_FRAC) -> np.ndarray:
    array = np.abs(np.asarray(residual, dtype=np.float64))
    peak = float(array.max()) if array.size else 0.0
    threshold = max(float(floor), float(frac) * peak)
    return array > threshold


def residual_betti(frames: list[Any]) -> list[list[int]]:
    out: list[list[int]] = []
    for index in range(1, len(frames)):
        residual = frame_residual(frames[index], frames[index - 1])
        b0, b1 = betti_numbers(residual_mask(residual))
        out.append([int(b0), int(b1)])
    return out


def clip_check_metrics(frames: Any) -> dict[str, Any]:
    """Both metrics for a list of gray frames. Recorded; not gating."""
    seq = [np.asarray(frame, dtype=np.float64) for frame in (frames or [])]
    if len(seq) < 2:
        return {
            "version": METRICS_VERSION,
            "motion_phase_coherence": None,
            "moving_transitions": 0,
            "shifts": [],
            "betti": [],
            "betti_stable": None,
            "gating": False,
        }
    coherence = motion_phase_coherence(seq)
    betti = residual_betti(seq)
    moving = [pair for pair in betti if pair != [0, 0]]
    return {
        "version": METRICS_VERSION,
        "motion_phase_coherence": coherence["R"],
        "moving_transitions": coherence["moving_transitions"],
        "shifts": coherence["shifts"],
        "betti": betti,
        "betti_stable": (len({tuple(pair) for pair in moving}) <= 1) if moving else None,
        "gating": False,
    }


__all__ = [
    "METRICS_VERSION",
    "betti_numbers",
    "clip_check_metrics",
    "motion_phase_coherence",
    "order_parameter",
    "phase_shift",
    "residual_betti",
    "residual_mask",
]
