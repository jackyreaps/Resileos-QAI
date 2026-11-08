"""Explain and remember.

Explain: plain answer from hub rows, or a prompt to look up.
Remember: fact lines ready for the hub.
"""
from __future__ import annotations

from typing import Any


def explain(query: str, hub_rows: list[Any]) -> dict[str, Any]:
    if hub_rows:
        text = "; ".join(str(r) for r in hub_rows)
        return {"text": text, "source": "hub", "query": query}
    return {
        "text": f"Not in your hub yet. Look up: {query}",
        "source": "none",
        "query": query,
    }


def remember(subject: str, relation: str, obj: str) -> dict[str, str]:
    sub = subject if subject.startswith(("user:", "world:", "org:")) else f"user:{subject}"
    return {"subject": sub, "relation": relation, "obj": obj}
