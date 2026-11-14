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
The address places it; it never dims it. Each instance carries its
frame's span as a block-size label (36/3 = 12, 36/9 = 4, 36/12 = 3;
the 5-frame is orientation only, no span). The span is a structural
block division, not a cap on children. The waist of 36 is the only
total limit: recursion runs through frame 12 and stops only at 36
copies in the sector, past 12, or when a sub-instance's own residual
energy is under 1/64 (``keep_packet``).

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


def _same_shape(pics: list[np.ndarray]) -> list[np.ndarray]:
    h = min(p.shape[0] for p in pics)
    w = min(p.shape[1] for p in pics)
    c = max(p.shape[2] if p.ndim == 3 else 1 for p in pics)
    out = []
    for p in pics:
        q = spread(grid(p, CASCADE_FRAMES[-1]), (h, w) + p.shape[2:]) if p.shape[:2] != (h, w) and min(p.shape[:2]) < max(h, w) else p[:h, :w]
        if c == 3 and q.ndim == 2:
            q = np.repeat(q[..., None], 3, axis=2)
        out.append(q)
    return out


def _phase_mix(a: np.ndarray, b: np.ndarray, t: float, shift: tuple[int, int] = (0, 0)) -> np.ndarray:
    """One band, one in-between: lerp the Fourier magnitude, and move the
    phase from ``a`` to ``b``. A shifted pattern moves instead of
    cross-fading. ``shift`` is the dominant (dy, dx) motion: the phase
    change is unwrapped around that motion's phase ramp, so a move larger
    than half a wavelength still travels the right way (a whole-picture
    stand-in for coarse-to-fine phase correction)."""
    fa, fb = np.fft.fft2(a, axes=(0, 1)), np.fft.fft2(b, axes=(0, 1))
    ma, mb = np.abs(fa), np.abs(fb)
    pa = np.angle(fa)
    h, w = a.shape[:2]
    ky = np.fft.fftfreq(h)[:, None]
    kx = np.fft.fftfreq(w)[None, :]
    ramp = -2 * np.pi * (ky * shift[0] + kx * shift[1])
    if a.ndim == 3:
        ramp = ramp[..., None]
    raw = np.angle(fb) - pa
    dp = ramp + np.angle(np.exp(1j * (raw - ramp)))  # wrapped around the motion
    mixed = ((1 - t) * ma + t * mb) * np.exp(1j * (pa + t * dp))
    return np.real(np.fft.ifft2(mixed, axes=(0, 1)))


def phase_inbetween(first: Any, second: Any, t: float) -> np.ndarray:
    """In-between of two keyframes at time ``t`` in [0, 1], level by level.

    Both pictures are leveled down to the same cascade bands (3, 5, 9, 12
    and the detail left over the 12-frame). Each band is mixed in the
    Fourier domain: magnitudes lerp, phases move from one keyframe to the
    other (phase-based interpolation, Meyer et al. 2015, on cascade bands
    instead of a steerable pyramid), unwrapped around the dominant motion
    from phase correlation. The bands are summed back. Every band is
    mixed at full strength: the address orders the levels, it is never a
    gain. t = 0 and t = 1 give the keyframes back exactly.
    """
    from resileos.studio.clip_metrics import phase_shift

    a, b = _same_shape([_as_array(first), _as_array(second)])
    t = float(min(1.0, max(0.0, t)))
    if t == 0.0:
        return a
    if t == 1.0:
        return b
    ga = a.mean(axis=2) if a.ndim == 3 else a
    gb = b.mean(axis=2) if b.ndim == 3 else b
    dy, dx, _ = phase_shift(ga, gb)
    la, lb = level_down(a), level_down(b)
    out = np.zeros_like(a)
    for ba, bb in zip(la["bands"], lb["bands"]):
        out = out + _phase_mix(ba["band"], bb["band"], t, (dy, dx))
    out = out + _phase_mix(la["detail"], lb["detail"], t, (dy, dx))
    return np.clip(out, 0.0, 1.0)


def phase_clip(keys: list[Any], *, per: int = 4, holds: Optional[list[int]] = None, cap: int = 24) -> list[np.ndarray]:
    """Keyframes to a clip with phase-based in-betweens.

    Same time steps as the existing blends: between keyframe i and i+1
    the in-betweens sit at t = j / per for j = 1 .. per-1, and keyframe i
    is held ``holds[i]`` frames (default 1). At most ``cap`` frames.
    """
    pics = _same_shape([_as_array(k) for k in keys])
    if len(pics) < 2:
        raise ValueError("a clip needs at least two keyframes")
    per = max(1, int(per))
    holds = list(holds or [1] * len(pics))
    seq: list[np.ndarray] = []
    for i, p in enumerate(pics):
        seq.extend([p] * max(1, int(holds[i] if i < len(holds) else 1)))
        if i + 1 < len(pics):
            seq.extend(phase_inbetween(p, pics[i + 1], j / per) for j in range(1, per))
    return seq[:cap]


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


# ── environments: leveled wave function collapse ──────────────────────
# Region layout at frame 3 and scene tiles at frame 9, on the waist
# lattice of 36: a frame-3 block is 12 units (3 × 3 blocks), a frame-9
# block is 4 units (9 × 9 blocks), so each region holds exactly 3 × 3
# scene tiles. Places and factions sit at frame 5, the orientation
# frame, which has no span: they are placed in a region, not tiled.
# Frame-12 detail tiles are not built: 12-blocks (3 units) do not nest
# in 9-blocks (4 units), and how a detail tile inherits from the scene
# tiles it straddles is an open choice (see docs/studio/studio-app.md).
REGION_TILES: dict[str, dict[str, Any]] = {
    "sea": {"next": {"sea", "coast"}, "holds": {"water"}, "weight": 3},
    "coast": {"next": {"sea", "coast", "plain"}, "holds": {"water", "sand", "grass"}, "weight": 2},
    "plain": {"next": {"coast", "plain", "forest", "hills"}, "holds": {"grass", "trees", "sand"}, "weight": 3},
    "forest": {"next": {"plain", "forest", "hills"}, "holds": {"trees", "grass"}, "weight": 2},
    "hills": {"next": {"plain", "forest", "hills", "mountain"}, "holds": {"grass", "rock", "trees"}, "weight": 2},
    "mountain": {"next": {"hills", "mountain"}, "holds": {"rock", "snow"}, "weight": 1},
}
SCENE_TILES: dict[str, dict[str, Any]] = {
    "water": {"next": {"water", "sand"}, "color": (0.13, 0.38, 0.78), "weight": 3},
    "sand": {"next": {"sand", "water", "grass"}, "color": (0.93, 0.84, 0.55), "weight": 1},
    "grass": {"next": {"grass", "sand", "trees", "rock"}, "color": (0.38, 0.70, 0.30), "weight": 3},
    "trees": {"next": {"trees", "grass", "rock"}, "color": (0.13, 0.45, 0.20), "weight": 2},
    "rock": {"next": {"rock", "grass", "trees", "snow"}, "color": (0.55, 0.50, 0.45), "weight": 2},
    "snow": {"next": {"snow", "rock"}, "color": (0.95, 0.96, 0.98), "weight": 1},
}


def _rng(seed: Any) -> np.random.Generator:
    import hashlib

    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def wfc(size: int, tiles: dict[str, dict[str, Any]], *, seed: Any = 0,
        allowed: Optional[list[list[set[str]]]] = None, tries: int = WAIST) -> dict[str, Any]:
    """Wave function collapse on a ``size × size`` grid. Deterministic.

    Each cell starts with every tile (or ``allowed[i][j]``). The cell with
    the fewest options collapses first, weighted by tile weight; the
    choice is propagated to 4-neighbours through each tile's ``next``
    set (symmetric adjacency). A contradiction restarts with the next
    seed, at most ``tries`` times (the waist). Returns the grid, the
    attempts used, and ``ok``.
    """
    names = sorted(tiles)
    for attempt in range(max(1, tries)):
        rng = _rng(f"{seed}/{attempt}")
        cells = [[set(allowed[i][j]) if allowed else set(names) for j in range(size)] for i in range(size)]
        ok = True

        def propagate(stack: list[tuple[int, int]]) -> bool:
            while stack:
                i, j = stack.pop()
                reach = set().union(*(tiles[t]["next"] for t in cells[i][j])) if cells[i][j] else set()
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    y, x = i + di, j + dj
                    if 0 <= y < size and 0 <= x < size:
                        keep = cells[y][x] & reach
                        if keep != cells[y][x]:
                            if not keep:
                                return False
                            cells[y][x] = keep
                            stack.append((y, x))
            return True

        if not propagate([(i, j) for i in range(size) for j in range(size)]):
            ok = False
        while ok:
            open_cells = [(len(cells[i][j]), i, j) for i in range(size) for j in range(size) if len(cells[i][j]) > 1]
            if not open_cells:
                break
            fewest = min(n for n, _, _ in open_cells)
            pick = [(i, j) for n, i, j in open_cells if n == fewest]
            i, j = pick[int(rng.integers(len(pick)))]
            options = sorted(cells[i][j])
            w = np.array([float(tiles[t]["weight"]) for t in options])
            cells[i][j] = {options[int(rng.choice(len(options), p=w / w.sum()))]}
            ok = propagate([(i, j)])
        if ok and all(len(c) == 1 for row in cells for c in row):
            return {"grid": [[next(iter(c)) for c in row] for row in cells], "attempts": attempt + 1, "ok": True}
    return {"grid": None, "attempts": max(1, tries), "ok": False}


def adjacency_ok(grid_: list[list[str]], tiles: dict[str, dict[str, Any]]) -> bool:
    """Every 4-neighbour pair is allowed by the tile set."""
    n = len(grid_)
    for i in range(n):
        for j in range(len(grid_[i])):
            for y, x in ((i + 1, j), (i, j + 1)):
                if y < n and x < len(grid_[i]) and grid_[y][x] not in tiles[grid_[i][j]]["next"]:
                    return False
    return True


def environment(project: dict[str, Any], *, seed: Any = None) -> dict[str, Any]:
    """Build a world map level by level from the project's world bible.

    Frame 3: a 3 × 3 region layout by WFC. Frame 5: each place and faction
    is put in a land region (orientation frame, no span, no tiles).
    Frame 9: a 9 × 9 scene-tile layout by WFC, each tile limited to what
    its region holds, so each region's 3 × 3 tiles nest exactly. The map
    picture is the 36 × 36 waist lattice (4 × 4 cells per scene tile),
    colours at full strength. The scene graph is the overlay tree world
    (3) → places (5) → scenes (9) → shot assets (12).
    """
    seed = project.get("id") if seed is None else seed
    regions = wfc(CASCADE_FRAMES[0], REGION_TILES, seed=f"{seed}/regions")
    if not regions["ok"]:
        return {"ok": False, "reason": "the region layout could not be solved"}
    r = regions["grid"]
    per = CASCADE_FRAMES[2] // CASCADE_FRAMES[0]  # 3 scene tiles per region side
    allowed = [[set(REGION_TILES[r[i // per][j // per]]["holds"]) for j in range(CASCADE_FRAMES[2])]
               for i in range(CASCADE_FRAMES[2])]
    scene = wfc(CASCADE_FRAMES[2], SCENE_TILES, seed=f"{seed}/scene", allowed=allowed)
    if not scene["ok"]:
        return {"ok": False, "reason": "the scene tiles could not be solved", "regions": r}
    t = scene["grid"]
    bible = project.get("bible") or {}
    land = [(i, j) for i in range(len(r)) for j in range(len(r)) if r[i][j] != "sea"] or [(1, 1)]
    placed = []
    for k, item in enumerate(list(bible.get("places") or []) + list(bible.get("factions") or [])):
        i, j = land[k % len(land)]
        placed.append({"id": item.get("id"), "name": item.get("name"),
                       "kind": "place" if k < len(bible.get("places") or []) else "faction",
                       "region": [i, j], "region_kind": r[i][j], "frame": 5})
    cell = WAIST // CASCADE_FRAMES[2]
    pic = np.zeros((WAIST, WAIST, 3))
    for i in range(CASCADE_FRAMES[2]):
        for j in range(CASCADE_FRAMES[2]):
            pic[i * cell:(i + 1) * cell, j * cell:(j + 1) * cell] = SCENE_TILES[t[i][j]]["color"]
    nest = all(t[i][j] in REGION_TILES[r[i // per][j // per]]["holds"]
               for i in range(CASCADE_FRAMES[2]) for j in range(CASCADE_FRAMES[2]))
    scenes = project.get("scenes") or []
    tree = Overlay(str(project.get("name") or "world"), children=[
        Overlay(str(p.get("name") or p.get("id")), children=[
            Overlay(str(s.get("title") or s.get("id")), children=[Overlay(str(sh.get("asset"))) for sh in s.get("shots") or []])
            for s in scenes if s.get("place") and s.get("place") == p.get("id")])
        for p in placed if p["kind"] == "place"])
    return {
        "ok": True,
        "regions": {"frame": frame_control(CASCADE_FRAMES[0]), "grid": r, "attempts": regions["attempts"],
                    "adjacency_ok": adjacency_ok(r, REGION_TILES)},
        "places": placed,
        "tiles": {"frame": frame_control(CASCADE_FRAMES[2]), "grid": t, "attempts": scene["attempts"],
                  "adjacency_ok": adjacency_ok(t, SCENE_TILES), "nested_in_regions": nest},
        "detail": {"frame": frame_control(CASCADE_FRAMES[3]), "built": False,
                   "reason": "frame-12 tiles straddle frame-9 tiles; the inheritance rule is an open choice"},
        "map": pic,
        "scene_graph": instances(tree),
    }


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
    φ address relative to frame 3 (an address, not a gain) and its span
    as block-size metadata (None at the 5-frame, orientation only). The
    span never limits fan-out. Stops: 36 copies in the sector (the waist,
    the only total limit), past the 12-frame, or a sub-instance whose own
    residual energy is under 1/64. The address never stops anything.
    """
    flat: list[dict[str, Any]] = []
    stopped = {"floor": 0, "waist": 0, "depth": 0}

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
        for i, child in enumerate(node.children):
            walk(child, depth + 1, f"{path}/{i}")

    walk(root, 0, "0")
    return {"instances": flat, "stopped": stopped, "floor": EPSILON, "waist": WAIST}
