"""Dionysus — a Hermes legion for vine and wine branching.

It expands a prompt into synonym, root, and translation neighbours
with hypervector bind and bundle. The vectors live in the latent hub.
This legion does not write to Titanos.
"""
from __future__ import annotations

import re
from typing import Any

from resileos.kin.legions import register_legion
from resileos.latent_hub import LatentHub

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_']*")

# Small closed tables. They are not a translator and not a model.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "father": ("parent", "dad"),
    "mother": ("parent", "mom"),
    "parent": ("father", "mother"),
    "child": ("offspring", "kid"),
    "job": ("work", "works_at"),
    "work": ("job", "works_at"),
    "city": ("town", "located_in"),
    "big": ("large",),
    "small": ("little",),
}
_ROOTS: dict[str, str] = {
    "parental": "parent",
    "fatherly": "father",
    "childhood": "child",
    "working": "work",
    "workers": "work",
}
_TRANSLATIONS: dict[str, str] = {
    "pere": "father",
    "padre": "father",
    "mere": "mother",
    "madre": "mother",
    "enfant": "child",
    "hijo": "child",
    "travail": "work",
    "trabajo": "work",
}

_hub: LatentHub | None = None


def get_hub() -> LatentHub:
    global _hub
    if _hub is None:
        _hub = LatentHub()
    return _hub


def reset_hub() -> LatentHub:
    global _hub
    _hub = LatentHub()
    return _hub


def _tokens(prompt: str) -> list[str]:
    seen: list[str] = []
    for token in _TOKEN.findall(prompt or ""):
        low = token.lower()
        if low not in seen:
            seen.append(low)
    return seen


def neighbours_for(token: str) -> list[str]:
    """Synonym, root, and translation neighbours. The token itself is omitted."""
    key = token.lower()
    found: list[str] = []

    def add(value: str) -> None:
        low = value.lower()
        if low and low != key and low not in found:
            found.append(low)

    for item in _SYNONYMS.get(key, ()):
        add(item)
    root = _ROOTS.get(key)
    if root:
        add(root)
        for item in _SYNONYMS.get(root, ()):
            add(item)
    translated = _TRANSLATIONS.get(key)
    if translated:
        add(translated)
        for item in _SYNONYMS.get(translated, ()):
            add(item)
    for source, target in _TRANSLATIONS.items():
        if target == key:
            add(source)
    return found


def expand(prompt: str, hub: LatentHub | None = None) -> dict[str, Any]:
    """Expand a prompt. Writes only into the latent hub."""
    store = hub if hub is not None else get_hub()
    tokens = _tokens(prompt)
    neighbours: list[str] = []
    for token in tokens:
        for item in neighbours_for(token):
            if item not in neighbours and item not in tokens:
                neighbours.append(item)
    vector = store.bind_bundle([*tokens, *neighbours] or [prompt or ""])
    key = " ".join(tokens) or (prompt or "").strip().lower()
    if key:
        store.put(key, vector, kind="hypervector")
    return {
        "prompt": prompt,
        "tokens": tokens,
        "neighbours": neighbours,
        "stored_in": "latent_hub",
        "writes_titanos": False,
        "learned": False,
    }


def retrieve(prompt: str, contexts: list[Any], budget: Any, hub: LatentHub | None = None) -> list[Any]:
    """Re-rank caller-supplied items using neighbour tokens. Adds no rows."""
    from resileos.kin.hermes import make_hermes_navigator

    expanded = expand(prompt, hub)
    depth = int(getattr(budget, "max_depth", 2) or 2)
    items = int(getattr(budget, "max_items", 8) or 8)
    navigate, _handler = make_hermes_navigator(max_depth=depth, max_items=items)
    return list(navigate(contexts, budget, neighbours=expanded["neighbours"]))


def dionysus(seen: Any, **kwargs: Any) -> dict[str, Any]:
    """Legion entry. Ignores a Titanos handle and a learn function."""
    del seen
    kwargs.pop("learn_fn", None)
    kwargs.pop("titanos", None)
    hub = kwargs.get("hub")
    if hub is not None and not isinstance(hub, LatentHub):
        hub = None
    return expand(str(kwargs.get("prompt") or kwargs.get("text") or ""), hub)


def register_dionysus() -> str:
    """Register the legion on Hermes. Idempotent."""
    from resileos.kin.legions import LegionError, kin_catalogue

    names = {row["name"] for row in kin_catalogue("hermes")}
    if "dionysus" in names:
        return "dionysus"
    try:
        register_legion(
            "hermes",
            dionysus,
            name="dionysus",
            constraints={
                "action": "expand language neighbours",
                "writes_residual": False,
                "executes": True,
            },
        )
    except LegionError as exc:
        if "already" not in str(exc).lower():
            raise
    return "dionysus"
