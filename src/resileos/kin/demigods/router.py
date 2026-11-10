"""Thin router: search / summon / dismiss Demi-gods.

Fixed small tool surface. The roster stays in the package. Only the
chosen Demi-god enters the caller's ControlPacket.

Summon and dismiss mutate that packet, or a dict the caller keeps.
They do not write onto a throwaway copy. Guide ids match exactly
(``demigod:<name>``). Unknown names, path traversal, and an empty
roster fail closed.
"""
from __future__ import annotations

import re
from importlib.resources import files
from typing import Any

import resileos.harness.tools as harness_tools

from .hierarchy import DemigodError, DemigodHierarchyError, active_demigod

# Bare roster name. Slashes, dots, and parent segments never match.
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_GUIDE_TOKEN = "demigod:{name}"


def _guides_root():
    return files("resileos.kin.demigods").joinpath("guides")


def _reject_bad_name(name: str) -> str:
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise DemigodError(f"rejected demigod name: {name!r}")
    return name


def _iter_guide_names() -> list[str]:
    """Stems of ``guides/*.md`` inside this package. Never a cwd path."""
    root = _guides_root()
    try:
        entries = list(root.iterdir())
    except (FileNotFoundError, OSError):
        return []
    names: list[str] = []
    for entry in entries:
        filename = entry.name
        if not filename.endswith(".md"):
            continue
        stem = filename[: -len(".md")]
        if _NAME.fullmatch(stem) is None:
            continue
        if entry.is_file():
            names.append(stem)
    return sorted(names)


def _require_roster() -> list[str]:
    names = _iter_guide_names()
    if not names:
        raise DemigodError("empty demigod roster")
    return names


def _read_guide(name: str) -> str:
    """Read one guide by exact directory-entry name. No path join on user input."""
    wanted = f"{name}.md"
    for entry in _guides_root().iterdir():
        if entry.name == wanted and entry.is_file():
            return entry.read_text(encoding="utf-8")
    raise DemigodError(f"unknown demigod: {name}")


def _description(text: str, fallback: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    desc = lines[1] if len(lines) > 1 else fallback
    return desc[:160]


def guide_token(name: str) -> str:
    return _GUIDE_TOKEN.format(name=name)


def list_demigods() -> list[dict[str, str]]:
    """Return name + one-line description of every Demi-god.

    An empty roster raises. It does not look like a successful empty list.
    """
    out: list[dict[str, str]] = []
    for name in _require_roster():
        text = _read_guide(name)
        out.append({"name": name, "description": _description(text, name)})
    return out


def demigod_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Search Demi-gods by name or description (simple substring).

    A blank query fails closed so a search cannot dump the roster.
    """
    roster = list_demigods()
    q = (query or "").strip().lower()
    if not q:
        raise DemigodError("empty demigod search")
    hits = [
        item
        for item in roster
        if q in item["name"].lower() or q in item["description"].lower()
    ]
    cap = limit if isinstance(limit, int) and limit > 0 else 0
    return {"query": query, "results": hits[:cap]}


def demigod_summon(name: str, packet: Any = None) -> dict[str, Any]:
    """Load one Demi-god guide into the caller's packet.

    The persona text is capped and stored on ``guide_bodies`` under the
    exact id ``demigod:<name>``. ``guides_loaded`` records that same id.
    """
    current = active_demigod()
    if current is not None:
        raise DemigodHierarchyError(
            f"demigod {current} cannot summon another demigod"
        )
    if packet is None:
        raise DemigodError("demigod_summon requires a packet")
    safe = _reject_bad_name(name)
    roster = _require_roster()
    if safe not in roster:
        raise DemigodError(f"unknown demigod: {safe}")
    body = _read_guide(safe)
    token = guide_token(safe)
    # Cap is read at call time so tests and callers share one limit.
    loaded = harness_tools.guide_load(
        [token],
        packet,
        bodies={token: body},
        body_cap=harness_tools.GUIDE_BODY_CAP,
    )
    stored = loaded["bodies"].get(token, "")
    return {
        "summoned": True,
        "demigod": safe,
        "guide": f"resileos.kin.demigods.guides/{safe}.md",
        "preview": stored[:400],
        "body_chars": len(stored),
        "hierarchy": "serves under Iris/Metis/Hermes/Apollo/Hades",
    }


def demigod_dismiss(name: str, packet: Any = None) -> dict[str, Any]:
    """Remove one Demi-god guide. Match the guide id exactly."""
    if packet is None:
        return {"dismissed": False, "reason": "no packet"}
    safe = _reject_bad_name(name)
    roster = _require_roster()
    if safe not in roster:
        raise DemigodError(f"unknown demigod: {safe}")
    token = guide_token(safe)
    loaded, stored = harness_tools._guide_containers(packet)
    if token not in loaded:
        return {
            "dismissed": False,
            "demigod": safe,
            "reason": "not summoned",
            "remaining": list(loaded),
        }
    # In-place so a dict from ControlPacket.to_dict() updates the packet.
    loaded[:] = [item for item in loaded if item != token]
    stored.pop(token, None)
    return {"dismissed": True, "demigod": safe, "remaining": list(loaded)}
