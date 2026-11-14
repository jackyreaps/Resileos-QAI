"""One leveled core for every Studio tool: image, video, and world.

The core mirrors the Resileos cascade. A level is a cascade frame
(3, 5, 9, 12) at its φ address (``cascade_address.frame_control``), not a
halving pyramid: frame f splits a picture into an f × f grid of cells,
so the levels are 3×3, 5×5, 9×9 and 12×12 and never a power of two.
Scaling and decompression are *leveling*: ``level_down`` analyses a
node into a base plus one band per frame, ``level_up`` / ``decode``
puts the bands back up to a chosen frame. The 5-frame is the
orientation (the pentagram figure, no waist span); 3, 9 and 12 divide
the waist of 36.

*Overlays* control recursive sub-instances. An overlay is a layer with a
strength order and an alpha ("over" composition for pixels, stronger
opinion wins for structured data). A sub-instance sits one frame out
from its parent, at that frame's φ address (relative to frame 3 = 1).
The address places it; it never dims it. What shrinks outward is the
waist span (36/3 = 12, 36/9 = 4, 36/12 = 3 children; the 5-frame is
the orientation, no span). Recursion runs through frame 12 and stops
only past 12, past the waist of 36, or when a sub-instance's own
residual energy is under 1/64 (``keep_packet``).

The same three verbs serve all pillars:

- image: bands are spatial (frame f = f × f cells);
- video: bands are temporal (frame f = f keyframes) plus spatial per frame;
- world: bands are depth (3 world/region, 5 place/faction, 9 scene,
  12 asset/detail).

This module never learns, never writes a scar, and never writes Titanos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np

from resileos.ui.cascade_address import (
    CASCADE_FRAMES,
    EPSILON,
    WAIST,
    frame_control,
    frame_weight,
    keep_packet,
    phi_address,
)

MAX_SIDE = 256
WORLD_DEPTH = {3: "world", 5: "place", 9: "scene", 12: "asset"}


# ── spatial leveling ───────────────────────────────────────────────────

def _as_array(matrix: Any) -> np.ndarray:
    arr = np.asarray(matrix, dtype=np.float64)
    if arr.ndim not in (2, 3) or arr.shape[0] == 0 or arr.shape[1] == 0:
        raise ValueError("expected an H×W or H×W×C picture")
    if arr.size and float(np.nanmax(arr)) > 1.0:
        arr = arr / 255.0
    arr = np.nan_to_num(np.clip(arr, 0.0, 1.0))
    h, w = arr.shape[:2]
    if h > MAX_SIDE or w > MAX_SIDE:
        sy, sx = -(-h // MAX_SIDE), -(-w // MAX_SIDE)
        arr = arr[::sy, ::sx]
    return arr


def _splits(n: int, f: int) -> list[np.ndarray]:
    return np.array_split(np.arange(n), min(f, n))


def grid(matrix: Any, frame: int) -> np.ndarray:
    """Mean of each cell of an ``frame × frame`` grid (fewer on tiny pictures)."""
    phi_address(frame)  # raises on a non-frame
    arr = _as_array(matrix)
    rows, cols = _splits(arr.shape[0], frame), _splits(arr.shape[1], frame)
    out = np.zeros((len(rows), len(cols)) + arr.shape[2:])
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            out[i, j] = arr[r][:, c].mean(axis=(0, 1))
    return out


def spread(cells: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """Put a cell grid back at full size (each cell fills its block)."""
    rows, cols = _splits(shape[0], cells.shape[0]), _splits(shape[1], cells.shape[1])
    out = np.zeros(shape[:2] + cells.shape[2:])
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            out[np.ix_(r, c)] = cells[i, j]
    return out


def level_down(matrix: Any) -> dict[str, Any]:
    """Analyse a picture into a base (frame 3) plus one band per frame.

    ``bands[k]`` is what frame ``CASCADE_FRAMES[k]`` adds over the frame
    before it; ``detail`` is what is left over the 12-frame. Each band
    records its frame control, its energy (mean |band|) and whether that
    energy clears the 1/64 floor.
    """
    arr = _as_array(matrix)
    previous = np.zeros_like(arr)
    bands = []
    for f in CASCADE_FRAMES:
        here = spread(grid(arr, f), arr.shape)
        band = here - previous
        energy = float(np.mean(np.abs(band)))
        bands.append({"frame": f, "control": frame_control(f), "address": round(frame_weight(f), 6),
                      "energy": round(energy, 6), "kept": f == CASCADE_FRAMES[0] or keep_packet(energy),
                      "band": band})
        previous = here
    detail = arr - previous
    return {"shape": list(arr.shape), "bands": bands, "detail": detail,
            "detail_energy": round(float(np.mean(np.abs(detail))), 6)}


def level_up(levels: dict[str, Any], frame: int, *, detail: bool = False) -> np.ndarray:
    """Decode up to ``frame``: the base plus every kept band through it."""
    phi_address(frame)
    out = np.zeros(tuple(levels["shape"]))
    for b in levels["bands"]:
        if b["frame"] > frame:
            break
        if b["kept"]:
            out = out + b["band"]
    if detail and frame == CASCADE_FRAMES[-1]:
        out = out + levels["detail"]
    return np.clip(out, 0.0, 1.0)


def decode(matrix: Any, frame: int, *, detail: bool = False) -> dict[str, Any]:
    """One call: level a picture down and back up to ``frame``."""
    levels = level_down(matrix)
    out = level_up(levels, frame, detail=detail)
    return {
        "matrix": np.round(out, 4).tolist(),
        "frame": frame_control(frame),
        "bands": [{k: v for k, v in b.items() if k != "band"} for b in levels["bands"]],
        "detail_energy": levels["detail_energy"],
    }


# ── temporal leveling ──────────────────────────────────────────────────

def keyframes(count: int, frame: int) -> list[int]:
    """Indices of the ``frame`` keyframes in a clip of ``count`` frames."""
    phi_address(frame)
    if count <= 0:
        return []
    k = min(frame, count)
    return sorted({int(round(i * (count - 1) / max(1, k - 1))) for i in range(k)})


def clip_at(frames: Iterable[Any], frame: int) -> dict[str, Any]:
    """Level a clip to ``frame`` keyframes; in-betweens are linear blends.

    Keyframes come first, in-betweens fill the rest, so a short preview
    is the 3-frame clip and the full clip is the 12-frame one.
    """
    seq = [_as_array(f) for f in frames]
    if len(seq) < 2:
        raise ValueError("a clip needs at least two frames")
    keys = keyframes(len(seq), frame)
    out = []
    for t in range(len(seq)):
        if t in keys:
            out.append(seq[t])
            continue
        lo = max(k for k in keys if k < t)
        hi = min(k for k in keys if k > t)
        a = (t - lo) / (hi - lo)
        out.append((1 - a) * seq[lo] + a * seq[hi])
    return {"frames": [np.round(f, 4).tolist() for f in out], "keyframes": keys, "frame": frame_control(frame)}


# ── world leveling ─────────────────────────────────────────────────────

def world_depth(frame: int) -> str:
    phi_address(frame)
    return WORLD_DEPTH[frame]


def world_at(project: dict[str, Any], frame: int) -> dict[str, Any]:
    """The world graph loaded to depth ``frame``: 3 world, 5 places and
    factions, 9 scenes, 12 assets."""
    phi_address(frame)
    bible = project.get("bible") or {}
    nodes = [{"depth": 3, "kind": "world", "id": project.get("id"), "name": project.get("name")}]
    if frame >= 5:
        nodes += [{"depth": 5, "kind": "place", "id": p.get("id"), "name": p.get("name")} for p in bible.get("places") or []]
        nodes += [{"depth": 5, "kind": "faction", "id": p.get("id"), "name": p.get("name")} for p in bible.get("factions") or []]
    if frame >= 9:
        nodes += [{"depth": 9, "kind": "scene", "id": s.get("id"), "name": s.get("title")} for s in project.get("scenes") or []]
    if frame >= 12:
        nodes += [{"depth": 12, "kind": "asset", "id": a.get("id"), "name": a.get("name")} for a in project.get("assets") or []]
    return {"frame": frame_control(frame), "depth": WORLD_DEPTH[frame], "nodes": nodes[:WAIST * 4]}


# ── overlays and recursive sub-instances ───────────────────────────────

@dataclass
class Overlay:
    """One layer: stronger layers sit on top; alpha is its coverage."""

    name: str
    strength: int = 0
    alpha: float = 1.0
    payload: Any = None
    children: list["Overlay"] = field(default_factory=list)
    energy: Optional[float] = None  # residual energy, if known; floored at 1/64


def over(base: np.ndarray, top: np.ndarray, alpha: float) -> np.ndarray:
    """Porter–Duff "over" with a constant alpha."""
    a = float(min(1.0, max(0.0, alpha)))
    return top * a + base * (1.0 - a)


def compose(base: Any, overlays: Iterable[Overlay]) -> np.ndarray:
    """Composite picture overlays onto ``base`` weakest first."""
    out = _as_array(base)
    for layer in sorted(overlays, key=lambda o: o.strength):
        top = _as_array(layer.payload)
        if top.shape[:2] != out.shape[:2]:
            top = spread(grid(top, CASCADE_FRAMES[-1]), out.shape[:2] + top.shape[2:])
        if top.ndim != out.ndim:
            top = np.repeat(top[..., None], out.shape[2], axis=2) if out.ndim == 3 else top.mean(axis=2)
        out = over(out, top, layer.alpha)
    return out


def merge(base: dict[str, Any], overlays: Iterable[Overlay]) -> dict[str, Any]:
    """Structured data: a stronger layer's opinion overrides a weaker one."""
    out = dict(base)
    for layer in sorted(overlays, key=lambda o: o.strength):
        if isinstance(layer.payload, dict):
            out.update(layer.payload)
    return out


def instances(root: Overlay) -> dict[str, Any]:
    """Flatten recursive sub-instances, leveling out the cascade.

    Depth d runs at frame ``CASCADE_FRAMES[d]`` and carries that frame's
    φ address relative to frame 3 (an address, not a gain) and its waist
    span. A node takes at most ``waist_span`` children at its frame (the
    5-frame orientation has no span, so the waist of 36 caps it). Stops:
    past the 12-frame, past 36 instances in all, or a sub-instance whose
    own residual energy is under 1/64. The address never stops anything.
    """
    flat: list[dict[str, Any]] = []
    stopped = {"floor": 0, "waist": 0, "depth": 0, "span": 0}

    def walk(node: Overlay, depth: int, path: str) -> None:
        if depth >= len(CASCADE_FRAMES):
            stopped["depth"] += 1
            return
        if node.energy is not None and not keep_packet(node.energy):
            stopped["floor"] += 1
            return
        if len(flat) >= WAIST:
            stopped["waist"] += 1
            return
        f = CASCADE_FRAMES[depth]
        ctrl = frame_control(f)
        flat.append({"name": node.name, "path": path, "depth": depth, "frame": f,
                     "address": round(frame_weight(f), 6), "span": ctrl["span"], "strength": 1.0})
        room = ctrl["span"] if ctrl["span"] is not None else WAIST
        for i, child in enumerate(node.children):
            if i >= room:
                stopped["span"] += len(node.children) - room
                break
            walk(child, depth + 1, f"{path}/{i}")

    walk(root, 0, "0")
    return {"instances": flat, "stopped": stopped, "floor": EPSILON, "waist": WAIST}
