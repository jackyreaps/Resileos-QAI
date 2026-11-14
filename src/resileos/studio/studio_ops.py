"""Studio operations for the three pillars, all on the leveled core.

Every operation takes a project and returns (project, result). Results
are labelled unverified; nothing here learns, touches scars, or writes
Titanos. Pictures and clips come from the color code of the user's own
uploads (``cascade_tools``) and the leveled core (``level_core``); text
to video goes to the provider slot and says UNAVAILABLE when no provider
is configured. Progress is reported through ``on_step(label, status)``
so the stream layer can show it.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

from resileos.studio import level_core as core
from resileos.studio.projects import new_id
from resileos.ui.cascade_address import ORIENTATION_SCALES, CASCADE_FRAMES, frame_control, orientation_scale

MAX_BATCH = 12
STORE_SIDE = 96

Step = Callable[[str, str], None]


def _noop(label: str, status: str) -> None:  # pragma: no cover - default
    return None


def _small(matrix: Any) -> list:
    """Round and cap a picture for storage in the project file."""
    arr = np.asarray(matrix, dtype=np.float64)
    h, w = arr.shape[:2]
    if h > STORE_SIDE or w > STORE_SIDE:
        sy, sx = -(-h // STORE_SIDE), -(-w // STORE_SIDE)
        arr = arr[::sy, ::sx]
    return np.round(np.clip(arr, 0.0, 1.0), 3).tolist()


def _asset(project: dict[str, Any], aid: str) -> dict[str, Any]:
    for a in project.get("assets") or []:
        if a.get("id") == aid:
            return a
    raise ValueError("That picture or clip isn't in this project.")


def _picture(asset: dict[str, Any]) -> list:
    if asset.get("matrix") is not None:
        return asset["matrix"]
    if asset.get("frames"):
        return asset["frames"][0]
    raise ValueError(f"“{asset.get('name')}” has no picture data.")


def describe(matrix: Any, kind: str = "image", frames: Any = None) -> dict[str, Any]:
    """Color code and individual-pin address for a picture or clip."""
    from resileos.chat import cascade_tools as cascade

    arr = core._as_array(matrix)
    gray = arr.mean(axis=2) if arr.ndim == 3 else arr
    edges = float(np.mean(np.abs(np.diff(gray, axis=0)))) + float(np.mean(np.abs(np.diff(gray, axis=1)))) if min(gray.shape) > 1 else 0.0
    raw = {"mean_luma": float(gray.mean()), "edge_density": min(1.0, edges)}
    seq = [core._as_array(f) for f in frames] if frames else None
    if seq and len({f.shape for f in seq}) != 1:
        seq = None
    up = cascade.address_upload(kind, raw, matrix=None if seq else arr, frames=seq)
    return {"code": up["code"] or "", "address": up["address"], "orientation": (up.get("chroma_code") or {}).get("orientation")}


def add_asset(project: dict[str, Any], body: dict[str, Any], *, source: str = "upload", parent: str = "",
              on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    kind = "clip" if body.get("kind") == "clip" or body.get("frames") else "image"
    matrix = body.get("matrix")
    frames = body.get("frames")
    if matrix is None and not frames:
        raise ValueError("Add a picture or a clip.")
    on_step("Reading the picture", "running")
    first = matrix if matrix is not None else frames[0]
    info = describe(first, kind, frames)
    asset = {
        "id": new_id(), "kind": kind, "name": str(body.get("name") or kind)[:120], "thumb": str(body.get("thumb") or ""),
        "source": source, "verified": False, "code": info["code"], "address": info["address"], "parent": parent,
        "layers": list(body.get("layers") or []), "note": str(body.get("note") or "")[:500],
    }
    if matrix is not None:
        asset["matrix"] = _small(matrix)
    if frames:
        asset["frames"] = [_small(f) for f in list(frames)[:24]]
    project.setdefault("assets", []).append(asset)
    on_step("Added to the asset board", "done")
    return project, {"asset": asset}


# ── advanced image creation ────────────────────────────────────────────

def _recolor(matrix: Any, *, variant: int = 1, orientation: Optional[str] = None, code: Optional[str] = None) -> np.ndarray:
    from resileos.chat import cascade_tools as cascade
    from resileos.ui.chroma import expand_variations, unpack_code

    rgb = cascade._rgb(matrix)
    c = unpack_code(bytes.fromhex(code)) if code else cascade.code_from_picture(rgb)
    if orientation:
        orientation_scale(orientation)  # raises on an unknown scale
        c = {**c, "orientation": orientation}
    palettes = expand_variations(c)
    picks = cascade._spaced(len(palettes), max(1, variant + 1))
    return cascade._render(cascade.belt_coords(rgb), palettes[picks[-1] if variant > 0 else 0])


def apply_layer(matrix: Any, layer: dict[str, Any], project: dict[str, Any]) -> np.ndarray:
    kind = layer.get("kind")
    arr = core._as_array(matrix)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if kind == "recolor":
        return _recolor(arr, variant=int(layer.get("variant") or 1))
    if kind == "orientation":
        return _recolor(arr, variant=0, orientation=str(layer.get("scale") or "edge"))
    if kind == "tone":
        b = float(layer.get("brightness") or 0.0)
        c = float(layer.get("contrast") if layer.get("contrast") is not None else 1.0)
        return np.clip((arr - 0.5) * max(0.0, min(c, 3.0)) + 0.5 + max(-1.0, min(b, 1.0)), 0.0, 1.0)
    if kind == "flip":
        return arr[:, ::-1] if layer.get("axis", "h") == "h" else arr[::-1]
    if kind == "crop":
        h, w = arr.shape[:2]
        x, y = float(layer.get("x") or 0), float(layer.get("y") or 0)
        cw, ch = float(layer.get("w") or 1), float(layer.get("h") or 1)
        x0, y0 = int(max(0, min(x, 1)) * w), int(max(0, min(y, 1)) * h)
        x1, y1 = max(x0 + 1, int(min(1, x + cw) * w)), max(y0 + 1, int(min(1, y + ch) * h))
        return arr[y0:y1, x0:x1]
    if kind == "level":
        frame = int(layer.get("frame") or 12)
        return core.level_up(core.level_down(arr), frame, detail=bool(layer.get("detail")))
    if kind == "overlay":
        top = _picture(_asset(project, str(layer.get("asset") or "")))
        return core.compose(arr, [core.Overlay("overlay", strength=int(layer.get("strength") or 1),
                                               alpha=float(layer.get("alpha") if layer.get("alpha") is not None else 0.5),
                                               payload=top)])
    raise ValueError(f"Unknown edit: {kind!r}")


def edit(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply a stack of layers to one or more pictures (a batch)."""
    ids = list(body.get("assets") or ([body["asset"]] if body.get("asset") else []))[:MAX_BATCH]
    layers = [l for l in list(body.get("layers") or [])[:12] if isinstance(l, dict)]
    if not ids or not layers:
        raise ValueError("Pick at least one picture and one edit.")
    made = []
    for i, aid in enumerate(ids, start=1):
        src = _asset(project, aid)
        on_step(f"Editing {i} of {len(ids)}", "running")
        out = _picture(src)
        for layer in layers:
            out = apply_layer(out, layer, project)
        project, res = add_asset(project, {"matrix": out, "name": f"{src['name']} (edited)", "layers": layers},
                                 source="made", parent=aid)
        made.append(res["asset"])
    on_step(f"Made {len(made)} edited picture{'s' if len(made) != 1 else ''}", "done")
    return project, {"made": made, "verified": False}


def variations(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    """Color-code variations of a picture, optionally at an orientation scale."""
    from resileos.chat import cascade_tools as cascade

    src = _asset(project, str(body.get("asset") or ""))
    n = max(1, min(int(body.get("n") or 4), 6))
    orientation = body.get("orientation")
    if orientation and orientation not in ORIENTATION_SCALES:
        raise ValueError("Unknown scale.")
    on_step("Expanding the color code", "running")
    code = src.get("code") or None
    if orientation:
        from resileos.ui.chroma import pack_code, unpack_code

        base = unpack_code(bytes.fromhex(code)) if code else cascade.code_from_picture(_picture(src))
        code = pack_code({**base, "orientation": orientation}).hex()
    out = cascade.variations_from_code(_picture(src), n=n, code=code)
    made = []
    for i, v in enumerate(out["variations"], start=1):
        project, res = add_asset(project, {"matrix": v["matrix"], "name": f"{src['name']} · variation {i}",
                                           "layers": [{"kind": "recolor", "rotation": v["rotation"], "hue_step": v["hue_step"],
                                                       "orientation": v["orientation"]}]},
                                 source="made", parent=src["id"])
        made.append(res["asset"])
    on_step(f"Made {len(made)} variations", "done")
    return project, {"made": made, "verified": False, "details": {"palettes": out["palettes_available"], "method": out["method"],
                                                                  "orientation": orientation_scale(orientation or "edge")}}


def pick(project: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare and pick: keep the chosen one, remember the choice."""
    winner = str(body.get("asset") or "")
    _asset(project, winner)
    picks = [p for p in project.get("picks") or [] if p != winner]
    project["picks"] = [winner] + picks
    return project, {"picked": winner}


def level_preview(project: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Show one picture at each cascade level (3, 5, 9, 12)."""
    src = _asset(project, str(body.get("asset") or ""))
    levels = core.level_down(_picture(src))
    out = []
    for f in CASCADE_FRAMES:
        out.append({"frame": frame_control(f), "matrix": np.round(core.level_up(levels, f), 3).tolist()})
    return project, {"levels": out, "bands": [{k: v for k, v in b.items() if k != "band"} for b in levels["bands"]]}


# ── general video ──────────────────────────────────────────────────────

def _same_size(pictures: list[Any]) -> list[np.ndarray]:
    arrs = [core._as_array(p) for p in pictures]
    arrs = [np.repeat(a[..., None], 3, axis=2) if a.ndim == 2 else a[..., :3] for a in arrs]
    h, w = arrs[0].shape[:2]
    out = []
    for a in arrs:
        if a.shape[:2] != (h, w):
            ys = np.linspace(0, a.shape[0] - 1, h).round().astype(int)
            xs = np.linspace(0, a.shape[1] - 1, w).round().astype(int)
            a = a[np.ix_(ys, xs)]
        out.append(a)
    return out


def _metrics(seq: list[np.ndarray]) -> dict[str, Any]:
    from resileos.studio.clip_metrics import clip_check_metrics

    return clip_check_metrics([f.mean(axis=2) if f.ndim == 3 else f for f in seq])


def clip_from_pictures(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    """One picture: φ hue steps plus the φ motion step. Several: keyframes
    with phase-based in-betweens from Muse (native, on the leveled core)."""
    from resileos.chat import cascade_tools as cascade

    ids = list(body.get("assets") or [])[:12]
    if not ids:
        raise ValueError("Pick one or more pictures.")
    frames_out = max(3, min(int(body.get("frames") or 12), 24))
    on_step("Making the clip", "running")
    if len(ids) == 1:
        made = cascade.clip_from_code(_picture(_asset(project, ids[0])), frames=frames_out)
        seq = made["frames"]
        details = {"method": made["method"], "frame": made.get("frame_control"), "metrics": made.get("check_metrics")}
    else:
        pics = _same_size([_picture(_asset(project, a)) for a in ids])
        per = max(2, frames_out // len(pics))
        on_step("Muse: moving between your keyframes", "running")
        made = _muse({"kind": "clip", "keyframes": pics, "per": per, "cap": 24})
        seq = [np.asarray(f).tolist() for f in made["evidence"]["frames"]]
        frame = max(f for f in CASCADE_FRAMES if f <= max(CASCADE_FRAMES[0], len(pics)))
        details = {"method": made["evidence"]["method"], "frame": frame_control(frame),
                   "metrics": made["evidence"]["metrics"], "confidence": made["confidence"], "cost": made["cost"],
                   "source": made["generative_source"], "evidence_id": made["generative_evidence_id"]}
    project, res = add_asset(project, {"kind": "clip", "frames": seq, "name": str(body.get("name") or "Clip")},
                             source="made", parent=ids[0])
    on_step("Clip ready", "done")
    return project, {"made": [res["asset"]], "verified": False, "details": details}


def recolor_clip(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    src = _asset(project, str(body.get("asset") or ""))
    if not src.get("frames"):
        raise ValueError("Pick a clip to recolor.")
    on_step("Recoloring every frame", "running")
    frames = []
    variant = max(1, int(body.get("variant") or 1))
    for f in src["frames"]:
        frames.append(np.round(_recolor(f, variant=variant, code=src.get("code") or None), 3).tolist())
    project, res = add_asset(project, {"kind": "clip", "frames": frames, "name": f"{src['name']} · recolor {variant}"},
                             source="made", parent=src["id"])
    on_step("Recolored clip ready", "done")
    return project, {"made": [res["asset"]], "verified": False}


def storyboard_clip(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    """A scene's storyboard to a clip: each shot held, blended into the next."""
    scene = next((s for s in project.get("scenes") or [] if s.get("id") == body.get("scene")), None)
    if scene is None:
        raise ValueError("That scene isn't in this project.")
    shots = [s for s in scene.get("shots") or [] if s.get("asset")]
    if not shots:
        raise ValueError("Add pictures to the storyboard first.")
    on_step(f"Laying out {len(shots)} shots", "running")
    pics = _same_size([_picture(_asset(project, s["asset"])) for s in shots])
    holds = [int(s.get("hold") or 1) for s in shots]
    muse_out = None
    if len(pics) >= 2:
        # Each shot held, then two in-betweens at 1/3 and 2/3 (same steps as before), by Muse.
        on_step("Muse: moving between shots", "running")
        muse_out = _muse({"kind": "clip", "keyframes": pics, "per": 3, "holds": holds, "cap": 24})
        seq_np = [np.asarray(f) for f in muse_out["evidence"]["frames"]]
    else:
        seq_np = [pics[0]] * max(2, holds[0])
    seq = [np.round(f, 3).tolist() for f in seq_np]
    project, res = add_asset(project, {"kind": "clip", "frames": seq, "name": f"{scene['title'] or 'Scene'} · storyboard"},
                             source="made", parent=shots[0]["asset"])
    on_step("Storyboard clip ready", "done")
    details = {"shots": len(shots), "frames": len(seq),
               "metrics": muse_out["evidence"]["metrics"] if muse_out else _metrics(seq_np)}
    if muse_out:
        details.update({"confidence": muse_out["confidence"], "cost": muse_out["cost"], "source": muse_out["generative_source"]})
    return project, {"made": [res["asset"]], "verified": False, "details": details}


def text_to_video(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop,
                  forge: Optional[Callable[..., dict[str, Any]]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """From a description. Never faked.

    With a scene set in a place of this world, Muse makes it natively: a
    slow pan over the world's generated map, starting at that place (the
    words themselves are not turned into pictures). Without one, the
    provider slot is asked, and it is UNAVAILABLE (url None) when no
    provider is set up.
    """
    from resileos.kin.studio_tools import run_forge_video

    prompt = str(body.get("prompt") or "").strip()[:1500]
    if not prompt:
        raise ValueError("Describe the video.")
    if body.get("scene"):
        on_step("Muse: building the scene's world", "running")
        made = _muse({"kind": "text_video", "project": project, "scene": body.get("scene"), "prompt": prompt})
        if made["status"] == "MADE":
            frames = [np.asarray(f).tolist() for f in made["evidence"]["frames"]]
            scene = next(s for s in project.get("scenes") or [] if s.get("id") == body.get("scene"))
            project, res = add_asset(project, {"kind": "clip", "frames": frames,
                                               "name": f"{scene.get('title') or 'Scene'} · world pan"}, source="made")
            on_step("Clip ready", "done")
            return project, {"status": "MADE", "url": None, "made": [res["asset"]], "verified": False,
                             "summary": [made["evidence"]["method"] + ".", f"Starts at {made['evidence']['place']}."],
                             "details": {"confidence": made["confidence"], "cost": made["cost"],
                                         "source": made["generative_source"], "metrics": made["evidence"]["metrics"]}}
        on_step("Muse can't make this", "unavailable")
        return project, {"status": "UNAVAILABLE", "url": None, "made": [], "detail": made.get("reason") or "Muse couldn't make it."}
    on_step("Asking the video provider", "running")
    out = (forge or run_forge_video)(prompt, stage="draft", clip=True)
    status = str((out or {}).get("status") or "UNAVAILABLE")
    url = (out or {}).get("url")
    if status.upper() == "UNAVAILABLE" or not url:
        on_step("No video provider is set up", "unavailable")
        return project, {"status": "UNAVAILABLE", "url": None, "made": [],
                         "detail": (out or {}).get("detail") or "No video generator is configured on this host."}
    on_step("Video ready", "done")
    return project, {"status": "MADE", "url": url, "made": [], "verified": False}


# ── world building ─────────────────────────────────────────────────────

def _muse(brief: dict[str, Any]) -> dict[str, Any]:
    """Studio calls Muse (Apollo's generative leaf) explicitly."""
    from resileos.kin.studio_tools import run_muse

    return run_muse(brief)


_TILE_WORDS = {"sea": "sea", "coast": "coast", "plain": "plains", "forest": "forest", "hills": "hills", "mountain": "mountains"}


def build_world(project: dict[str, Any], body: dict[str, Any], on_step: Step = _noop) -> tuple[dict[str, Any], dict[str, Any]]:
    """Muse builds the world map: regions, where places sit, scene tiles,
    the scene graph, and the game checks. Saved as a picture asset."""
    on_step("Muse: laying out regions", "running")
    made = _muse({"kind": "environment", "project": project, "seed": body.get("seed")})
    if made["status"] != "MADE":
        on_step("Couldn't build the map", "error")
        return project, {"status": made["status"], "made": [], "detail": made.get("reason") or "Couldn't build the map."}
    ev = made["evidence"]
    on_step("Placing places and scene tiles", "running")
    project, res = add_asset(project, {"kind": "image", "matrix": np.asarray(ev["map"]).tolist(), "name": "World map"},
                             source="made")
    words = {"regions_fit": "Neighbouring regions fit together", "tiles_fit": "Neighbouring tiles fit together",
             "tiles_nest_in_regions": "Every tile fits its region", "game_rules_hold": "Game rules hold for 12 rounds",
             "timeline_fits": "The timeline has no clashes"}
    summary = [("✓ " if ok else "✗ ") + words.get(k, k) for k, ok in ev["checks"].items()]
    summary += [f"{p['name'] or 'Unnamed'} is in the {_TILE_WORDS.get(p['region_kind'], p['region_kind'])}" for p in ev["places"]]
    on_step("Map ready", "done")
    return project, {"status": "MADE", "made": [res["asset"]], "verified": False, "summary": summary,
                     "details": {"regions": ev["regions"]["grid"], "places": ev["places"], "checks": ev["checks"],
                                 "scene_graph": ev["scene_graph"], "detail_level": ev["detail"],
                                 "game": ev["game"], "lean_source": ev["lean_source"], "confidence": made["confidence"],
                                 "cost": made["cost"], "source": made["generative_source"],
                                 "evidence_id": made["generative_evidence_id"]}}


def world_check(project: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from resileos.studio.projects import check_game, check_timeline

    return project, {"timeline": check_timeline(project["bible"]["timeline"]), "game": check_game(project["game"])}


def world_level(project: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return project, core.world_at(project, int(body.get("frame") or 12))


def game_lean(project: dict[str, Any], body: dict[str, Any], lean_fn: Optional[Callable[[str], dict[str, Any]]] = None
              ) -> tuple[dict[str, Any], dict[str, Any]]:
    from resileos.studio.projects import game_lean_source

    source = game_lean_source(project["game"])
    if source is None:
        return project, {"status": "NOTHING", "summary": "Add whole-number stats or invariants to check."}
    if lean_fn is None:
        from resileos.verify.lean_check import check_lean as lean_fn  # type: ignore[assignment]
    out = lean_fn(source)
    return project, {"status": out.get("status"), "summary": out.get("summary"), "source": source}


def dream(project: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from resileos.studio.projects import dream as dream_ideas

    return project, dream_ideas(project, n=int(body.get("n") or 4), seed=int(body.get("seed") or 0))


def _iso(value: Optional[str], *, low: bool) -> str:
    """A year or month bound as a full date for Eat: start or end of it."""
    if not value:
        return ""
    import calendar

    neg = value.startswith("-")
    parts = value.lstrip("-").split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else (1 if low else 12)
    if len(parts) > 2:
        day = int(parts[2])
    else:
        day = 1 if low else calendar.monthrange(max(1, year), month)[1]
    return f"{'-' if neg else ''}{year:04d}-{month:02d}-{day:02d}"


def promote_preview(project: dict[str, Any], body: dict[str, Any], titanos: Any = None,
                    lean_fn: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Opt-in only. Show what Eat would do with the chosen timeline facts.

    Nothing is written here. The facts go into Eat only when an admin
    saves them from Admin → Knowledge → Add facts (Eat stays the only
    writer, with review).
    """
    if body.get("opt_in") is not True:
        raise ValueError("Turn on “Offer to shared knowledge” first.")
    from resileos.kin import knowledge_intake

    want = set(body.get("ids") or [])
    rows = [r for r in project["bible"]["timeline"] if not want or r["id"] in want]
    if not rows:
        raise ValueError("Pick timeline facts to offer.")
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["subject", "relation", "object", "valid_from", "valid_to"])
    for r in rows:
        w.writerow([r["subject"], r["relation"], r["object"], _iso(r.get("valid_from"), low=True), _iso(r.get("valid_to"), low=False)])
    text = buf.getvalue()
    preview = knowledge_intake.preview_items([{"name": f"{project['name'][:60]}.csv", "text": text}],
                                             titanos=titanos, lean_fn=lean_fn)
    return project, {"csv": text, "preview": preview, "saved": 0,
                     "note": "Nothing was saved. An admin can add these in Admin → Knowledge → Add facts, where Eat reviews them."}


OPS: dict[str, Callable[..., tuple[dict[str, Any], dict[str, Any]]]] = {
    "add_asset": lambda p, b, on_step=_noop: add_asset(p, b, source="chat" if b.get("from_chat") else "upload", on_step=on_step),
    "edit": edit,
    "variations": variations,
    "clip": clip_from_pictures,
    "recolor_clip": recolor_clip,
    "storyboard_clip": storyboard_clip,
    "text_to_video": text_to_video,
    "build_world": build_world,
}
