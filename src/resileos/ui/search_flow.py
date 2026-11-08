"""Search the hub first, then an optional web lookup.

Daily use: find something they do not understand.
If the hub has it, return it.
If not, look up and offer to save.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.scale_address import scale_address
from urllib.parse import quote_plus


def search_hub(ask: Callable[[str, str], Any], subject: str, relation: str = "status") -> list[Any]:
    row = ask(subject, relation)
    if row is None:
        return []
    if isinstance(row, list):
        return row
    return [row]


def web_search_url(query: str) -> str:
    """No API key. A results URL the UI can open or fetch."""
    return "https://duckduckgo.com/html/?q=" + quote_plus(query)


def search(
    query: str,
    *,
    ask: Optional[Callable[[str, str], Any]] = None,
    subject: str = "",
    relation: str = "status",
) -> dict[str, Any]:
    hub_rows: list[Any] = []
    if ask is not None and subject:
        hub_rows = search_hub(ask, subject, relation)
    addr = scale_address(subject=subject or query[:40])
    return {
        "query": query,
        "hub": hub_rows,
        "hub_hit": bool(hub_rows),
        "web_url": web_search_url(query),
        "offer_save": not hub_rows,
        "scale": {"address": addr["embed"], "gate": addr["gate"]},
    }
