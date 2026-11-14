"""Studio projects: one world per project, stored per account.

A project holds the three Studio pillars on one asset board:

- world building: a world bible (lore, places, factions, a timeline of
  quintuples with ``valid_from`` / ``valid_to``), characters linked to
  the persona store's individual tier, scenes and storyboards, and an
  open game system (stats, entities, rules, invariants, state);
- general video: a clip timeline over assets;
- advanced image creation: assets with color codes, cascade pin
  addresses, layers, variations and picks.

Projects live under ``RESILEOS_STUDIO_DIR/<owner hash>/`` (individual
tier: only the signed-in account sees them). Nothing here learns, writes
a scar, or writes Titanos. Promotion of timeline facts goes only through
Eat, and only when the owner opts in.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Optional

_REPO = Path(__file__).resolve().parents[3]
MAX_PROJECTS = 50
MAX_BYTES = 4 * 1024 * 1024
MAX_ITEMS = 200
MAX_TEXT = 4000
ID = re.compile(r"^[a-f0-9]{16}$")
SECTIONS = ("bible", "characters", "assets", "scenes", "game", "video", "picks")
LIST_SECTIONS = ("characters", "assets", "scenes")


def studio_root() -> Path:
    raw = os.getenv("RESILEOS_STUDIO_DIR", "").strip()
    return Path(raw) if raw else _REPO / "data" / "studio"


def _owner_dir(owner: str) -> Path:
    return studio_root() / hashlib.sha256(owner.encode("utf-8")).hexdigest()[:32]


def require_account(owner: str) -> None:
    if not owner or owner.startswith("trial:"):
        raise PermissionError("Sign in to keep Studio projects.")


def new_id() -> str:
    return secrets.token_hex(8)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value if value is not None else "")[:limit]


def _date(value: Any) -> Optional[str]:
    """ISO date (YYYY, YYYY-MM or YYYY-MM-DD) or None for an open bound."""
    s = str(value or "").strip()
    if not s:
        return None
    if not re.fullmatch(r"-?\d{1,6}(-\d{2}(-\d{2})?)?", s):
        raise ValueError(f"not a date: {s!r}")
    return s


def _date_key(s: Optional[str], *, low: bool) -> tuple:
    if s is None:
        return (float("-inf"),) if low else (float("inf"),)
    neg = s.startswith("-")
    parts = [int(p) for p in s.lstrip("-").split("-")]
    parts[0] = -parts[0] if neg else parts[0]
    while len(parts) < 3:
        parts.append(1 if low else 31 if len(parts) == 2 else 12)
    return tuple(parts)


def _items(rows: Any, clean: Callable[[dict[str, Any]], dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in list(rows or [])[:MAX_ITEMS]:
        if isinstance(row, dict):
            item = clean(row)
            item["id"] = str(row.get("id") or "")[:32] or new_id()
            out.append(item)
    return out


def _named(row: dict[str, Any]) -> dict[str, Any]:
    return {"name": _text(row.get("name"), 120), "notes": _text(row.get("notes"))}


def _timeline(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": _text(row.get("subject"), 200),
        "relation": _text(row.get("relation"), 120),
        "object": _text(row.get("object"), 200),
        "valid_from": _date(row.get("valid_from")),
        "valid_to": _date(row.get("valid_to")),
        "note": _text(row.get("note"), 500),
    }


def _character(row: dict[str, Any]) -> dict[str, Any]:
    from resileos.ui.cascade_address import pin_address

    pin = pin_address("individual")
    return {
        "name": _text(row.get("name"), 120),
        "role": _text(row.get("role"), 120),
        "notes": _text(row.get("notes")),
        "voice": _text(row.get("voice") or "honest", 40),
        # The persona store's individual tier, by pin. No promotion.
        "persona": {"tier": "individual", "pin": pin["path"], "promotes": False},
    }


def _asset(row: dict[str, Any]) -> dict[str, Any]:
    kind = row.get("kind") if row.get("kind") in ("image", "clip") else "image"
    out = {
        "kind": kind,
        "name": _text(row.get("name") or kind, 120),
        "thumb": _text(row.get("thumb"), 200_000) if str(row.get("thumb") or "").startswith("data:image/") else "",
        "source": row.get("source") if row.get("source") in ("upload", "made", "dream", "chat") else "upload",
        "verified": False,
        "code": _text(row.get("code"), 64),
        "address": row.get("address") if isinstance(row.get("address"), dict) else {},
        "parent": _text(row.get("parent"), 32),
        "layers": [l for l in list(row.get("layers") or [])[:12] if isinstance(l, dict)],
        "note": _text(row.get("note"), 500),
        "created_at": _text(row.get("created_at") or _now(), 32),
    }
    if isinstance(row.get("matrix"), list):
        out["matrix"] = row["matrix"]
    if isinstance(row.get("frames"), list):
        out["frames"] = row["frames"][:24]
    return out


def _scene(row: dict[str, Any]) -> dict[str, Any]:
    shots = []
    for s in list(row.get("shots") or [])[:36]:
        if isinstance(s, dict):
            shots.append({"asset": _text(s.get("asset"), 32), "note": _text(s.get("note"), 300),
                          "hold": max(1, min(int(s.get("hold") or 1), 12))})
    return {"title": _text(row.get("title"), 160), "summary": _text(row.get("summary")),
            "place": _text(row.get("place"), 32), "characters": [_text(c, 32) for c in list(row.get("characters") or [])[:36]],
            "shots": shots}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _game(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    stats = []
    for s in list(raw.get("stats") or [])[:36]:
        if isinstance(s, dict) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", str(s.get("name") or "")):
            stats.append({"name": s["name"], "min": _num(s.get("min")), "max": _num(s.get("max"), 100.0),
                          "start": _num(s.get("start"))})
    names = {s["name"] for s in stats}
    entities = []
    for e in list(raw.get("entities") or [])[:MAX_ITEMS]:
        if isinstance(e, dict):
            values = {k: _num(v) for k, v in dict(e.get("stats") or {}).items() if k in names}
            entities.append({"id": str(e.get("id") or new_id())[:32], "name": _text(e.get("name"), 120), "stats": values})
    rules = []
    for r in list(raw.get("rules") or [])[:MAX_ITEMS]:
        if isinstance(r, dict) and r.get("stat") in names:
            rules.append({"id": str(r.get("id") or new_id())[:32], "name": _text(r.get("name"), 120),
                          "stat": r["stat"], "change": _num(r.get("change")), "note": _text(r.get("note"), 300)})
    invariants = []
    for inv in list(raw.get("invariants") or [])[:36]:
        if isinstance(inv, dict) and inv.get("stat") in names and inv.get("op") in (">=", "<=", "=="):
            invariants.append({"id": str(inv.get("id") or new_id())[:32], "stat": inv["stat"], "op": inv["op"],
                               "value": _num(inv.get("value"))})
    return {"stats": stats, "entities": entities, "rules": rules, "invariants": invariants}


def clean(project: dict[str, Any]) -> dict[str, Any]:
    """Normalise a project to the stored schema. Raises ValueError."""
    bible = project.get("bible") if isinstance(project.get("bible"), dict) else {}
    out = {
        "id": str(project.get("id") or new_id()),
        "name": _text(project.get("name") or "Untitled world", 120),
        "summary": _text(project.get("summary"), 1000),
        "tier": "individual",
        "bible": {
            "lore": _items(bible.get("lore"), lambda r: {"title": _text(r.get("title"), 160), "text": _text(r.get("text"))}),
            "places": _items(bible.get("places"), _named),
            "factions": _items(bible.get("factions"), _named),
            "timeline": _items(bible.get("timeline"), _timeline),
        },
        "characters": _items(project.get("characters"), _character),
        "assets": _items(project.get("assets"), _asset),
        "scenes": _items(project.get("scenes"), _scene),
        "game": _game(project.get("game")),
        "video": {"timeline": [
            {"asset": _text(c.get("asset"), 32), "hold": max(1, min(int(c.get("hold") or 1), 12))}
            for c in list((project.get("video") or {}).get("timeline") or [])[:36] if isinstance(c, dict)
        ]},
        "picks": [_text(p, 32) for p in list(project.get("picks") or [])[:MAX_ITEMS]],
        "created_at": _text(project.get("created_at") or _now(), 32),
        "updated_at": _now(),
        "learned": False,
    }
    if not ID.fullmatch(out["id"]):
        raise ValueError("bad project id")
    if len(json.dumps(out)) > MAX_BYTES:
        raise ValueError("That project is too big to save. Remove some pictures or clips.")
    return out


# ── store ──────────────────────────────────────────────────────────────

def _path(owner: str, pid: str) -> Path:
    if not ID.fullmatch(pid or ""):
        raise KeyError(pid)
    return _owner_dir(owner) / f"{pid}.json"


def list_projects(owner: str) -> list[dict[str, Any]]:
    require_account(owner)
    folder = _owner_dir(owner)
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            p = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.append({"id": p["id"], "name": p["name"], "summary": p.get("summary", ""), "updated_at": p.get("updated_at"),
                     "counts": {k: len(p.get(k) or []) for k in LIST_SECTIONS}})
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return rows


def get_project(owner: str, pid: str) -> dict[str, Any]:
    require_account(owner)
    path = _path(owner, pid)
    if not path.exists():
        raise KeyError(pid)
    return json.loads(path.read_text(encoding="utf-8"))


def save_project(owner: str, project: dict[str, Any]) -> dict[str, Any]:
    require_account(owner)
    data = clean(project)
    folder = _owner_dir(owner)
    path = _path(owner, data["id"])
    if not path.exists() and len(list(folder.glob("*.json")) if folder.exists() else []) >= MAX_PROJECTS:
        raise ValueError(f"You can keep up to {MAX_PROJECTS} projects. Delete one first.")
    folder.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    return data


def delete_project(owner: str, pid: str) -> bool:
    require_account(owner)
    path = _path(owner, pid)
    if path.exists():
        path.unlink()
        return True
    return False


# ── world checks ───────────────────────────────────────────────────────

def check_timeline(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    """Bounds in order, and no two facts that disagree while both hold.

    Two entries conflict when they share subject and relation, name
    different objects, and their [valid_from, valid_to] spans overlap.
    """
    problems = []
    for row in timeline:
        if row.get("valid_from") and row.get("valid_to") and \
                _date_key(row["valid_from"], low=True) > _date_key(row["valid_to"], low=False):
            problems.append({"kind": "order", "ids": [row["id"]],
                             "text": f"“{row['subject']} {row['relation']} {row['object']}” ends before it starts."})
    for i, a in enumerate(timeline):
        for b in timeline[i + 1:]:
            if (a["subject"].lower(), a["relation"].lower()) != (b["subject"].lower(), b["relation"].lower()):
                continue
            if a["object"].strip().lower() == b["object"].strip().lower():
                continue
            if _date_key(a.get("valid_from"), low=True) <= _date_key(b.get("valid_to"), low=False) and \
                    _date_key(b.get("valid_from"), low=True) <= _date_key(a.get("valid_to"), low=False):
                problems.append({"kind": "overlap", "ids": [a["id"], b["id"]],
                                 "text": f"{a['subject']} {a['relation']} both “{a['object']}” and “{b['object']}” at the same time."})
    return {"ok": not problems, "problems": problems, "checked": len(timeline)}


def _holds(value: float, op: str, bound: float) -> bool:
    return value >= bound if op == ">=" else value <= bound if op == "<=" else value == bound


def check_game(game: dict[str, Any], *, steps: int = 12) -> dict[str, Any]:
    """Play every rule on every entity for ``steps`` rounds and check the
    invariants and the stat bounds after each round. Pure arithmetic."""
    stats = {s["name"]: s for s in game.get("stats") or []}
    problems = []
    for s in stats.values():
        if s["min"] > s["max"]:
            problems.append({"kind": "bounds", "text": f"{s['name']}: the lowest value is above the highest."})
        elif not (s["min"] <= s["start"] <= s["max"]):
            problems.append({"kind": "bounds", "text": f"{s['name']} starts outside its range."})
    entities = game.get("entities") or [{"id": "default", "name": "Default", "stats": {}}]
    for ent in entities:
        state = {n: float(ent.get("stats", {}).get(n, s["start"])) for n, s in stats.items()}
        for step in range(1, max(1, min(int(steps), 36)) + 1):
            for rule in game.get("rules") or []:
                s = stats[rule["stat"]]
                state[rule["stat"]] = min(s["max"], max(s["min"], state[rule["stat"]] + rule["change"]))
            for inv in game.get("invariants") or []:
                if not _holds(state[inv["stat"]], inv["op"], inv["value"]):
                    problems.append({"kind": "invariant", "entity": ent.get("name"), "round": step,
                                     "text": f"{ent.get('name') or 'An entity'}: {inv['stat']} {inv['op']} {inv['value']:g} breaks in round {step} ({state[inv['stat']]:g})."})
                    break
            else:
                continue
            break
    return {"ok": not problems, "problems": problems[:36], "rounds": steps, "entities": len(entities)}


def _lean_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else None  # type: ignore[return-value]


def game_lean_source(game: dict[str, Any]) -> Optional[str]:
    """A Lean file stating each stat's start sits in its range and each
    invariant holds at the start. Integer values only; ``None`` if none."""
    lines = ["-- Studio game system invariants (generated)"]
    n = 0
    stats = {s["name"]: s for s in game.get("stats") or []}
    for s in stats.values():
        lo, st, hi = _lean_num(s["min"]), _lean_num(s["start"]), _lean_num(s["max"])
        if None in (lo, st, hi):
            continue
        lines.append(f"theorem {s['name']}_start_in_range : ({lo} : Int) ≤ {st} ∧ ({st} : Int) ≤ {hi} := by decide")
        n += 1
    for i, inv in enumerate(game.get("invariants") or []):
        s = stats.get(inv["stat"])
        st, v = (_lean_num(s["start"]), _lean_num(inv["value"])) if s else (None, None)
        if None in (st, v):
            continue
        op = {">=": "≥", "<=": "≤", "==": "="}[inv["op"]]
        lines.append(f"theorem invariant_{i}_{inv['stat']}_at_start : ({st} : Int) {op} {v} := by decide")
        n += 1
    return "\n".join(lines) + "\n" if n else None


# ── dreams (Morpheus / Hypnos style): unverified ideas ─────────────────

def dream(project: dict[str, Any], *, n: int = 4, seed: int = 0) -> dict[str, Any]:
    """Recombine the world's own pieces into ``n`` labelled, unchecked ideas.

    Picks are spread by the golden-ratio sequence, so the same project
    and seed give the same dreams. Nothing is saved or learned.
    """
    from resileos.substrate.suite_constants import PHI

    bible = project.get("bible") or {}
    pools = {
        "place": [p["name"] for p in bible.get("places") or [] if p.get("name")],
        "faction": [p["name"] for p in bible.get("factions") or [] if p.get("name")],
        "character": [c["name"] for c in project.get("characters") or [] if c.get("name")],
    }
    ideas = []
    for k in range(max(1, min(int(n), 12))):
        pick = {}
        for j, (kind, pool) in enumerate(pools.items()):
            if pool:
                pick[kind] = pool[int((((seed + k + 1) * PHI + j * PHI * PHI) % 1.0) * len(pool))]
        if not pick:
            break
        bits = []
        if "character" in pick:
            bits.append(pick["character"])
        if "faction" in pick:
            bits.append(f"crosses {pick['faction']}" if bits else pick["faction"])
        if "place" in pick:
            bits.append(f"in {pick['place']}")
        ideas.append({"idea": " ".join(bits) + ".", "parts": pick, "verified": False, "label": "Dream — not checked"})
    return {"ideas": ideas, "verified": False, "learned": False,
            "note": "Dreams recombine your own world. They are ideas, not facts."}
