"""Execute resileos_* tools against Titanos (frontier mouth boundary).

External models may only call these tools. They must not invent answers
when status is NONE_CHANNEL / ABSTAINED / frame abstained|unresolved.
"""
from __future__ import annotations

from typing import Any, Optional

from .policy import derive_frame


def execute_tool(
    name: str,
    arguments: dict,
    *,
    titanos: Any,
) -> dict:
    """Run one tool call; always returns a structured Oracle result."""
    name = (name or "").strip()
    args = arguments or {}

    if name == "resileos_abstain":
        frame = "abstained"
        out = {
            "name": name,
            "status": "ABSTAINED",
            "frame": frame,
            "rows": [],
            "value": None,
            "reason": str(args.get("reason") or "explicit abstain"),
            "instruction": (
                "Do not invent an answer. Inform the user the information "
                "is unavailable or refused by the store."
            ),
        }
        return out

    if name == "resileos_ask":
        subject = str(args.get("subject") or args.get("anchor") or "").strip()
        relation = str(args.get("relation") or "").strip()
        inverse = bool(args.get("inverse", False))
        if not subject or not relation:
            return {
                "name": name,
                "status": "NONE_CHANNEL",
                "frame": "unresolved",
                "rows": [],
                "value": None,
                "reason": "missing subject/relation",
                "instruction": "Do not invent an answer.",
            }
        rows = list(titanos.ask_list(subject, relation, inverse=inverse))
        status = "ANSWERED" if rows else "NO_ROWS"
        frame = derive_frame(
            sector="gbx_like",
            status=status,
            n_rows=len(rows),
        )
        return {
            "name": name,
            "status": status,
            "frame": frame,
            "subject": subject,
            "relation": relation,
            "inverse": inverse,
            "rows": rows,
            "value": rows[0] if len(rows) == 1 else None,
            "reason": "" if rows else "no rows for triple",
            "instruction": (
                "Answer only from rows. If empty, say the store has no fact."
            ),
        }

    if name == "resileos_chain":
        subject = str(args.get("subject") or "").strip()
        hops = args.get("hops") or []
        if not subject or not hops:
            return {
                "name": name,
                "status": "NONE_CHANNEL",
                "frame": "unresolved",
                "rows": [],
                "value": None,
                "reason": "missing subject/hops",
                "instruction": "Do not invent an answer.",
            }
        try:
            ans = titanos.chain(subject, list(hops))
            value = getattr(ans, "value", None)
            path = list(getattr(ans, "path", []) or [])
            status = "ANSWERED" if value is not None else "NO_ROWS"
            frame = derive_frame(
                sector="otx_like",
                status=status,
                n_rows=1 if value is not None else 0,
            )
            return {
                "name": name,
                "status": status,
                "frame": frame,
                "subject": subject,
                "hops": list(hops),
                "value": value,
                "path": path,
                "rows": [value] if value is not None else [],
                "reason": getattr(ans, "reason", "") or "",
                "instruction": (
                    "Use value/path only. Do not invent intermediate hops."
                ),
            }
        except Exception as e:
            return {
                "name": name,
                "status": "NONE_CHANNEL",
                "frame": "unresolved",
                "rows": [],
                "value": None,
                "reason": f"chain failed: {e}",
                "instruction": "Do not invent an answer.",
            }

    if name == "resileos_answer":
        # Delegate shape only — caller should use /answer for full mouth.
        return {
            "name": name,
            "status": "NONE_CHANNEL",
            "frame": "unresolved",
            "rows": [],
            "value": None,
            "reason": "use POST /api/v1/answer for gate+mouth; tools execute supports ask/chain/abstain",
            "instruction": "Call resileos_ask or resileos_chain instead.",
        }

    if name == "resileos_sparql":
        q = str(args.get("query") or "").strip()
        if not q:
            return {
                "name": name,
                "status": "NONE_CHANNEL",
                "frame": "unresolved",
                "rows": [],
                "value": None,
                "reason": "missing query",
                "instruction": "Do not invent an answer.",
            }
        try:
            # Prefer query engine if present on app; fallback message
            return {
                "name": name,
                "status": "NO_ROWS",
                "frame": "reconstructed",
                "rows": [],
                "value": None,
                "reason": "sparql execute via /api/v1/sparql preferred",
                "query": q,
                "instruction": "Use the SPARQL HTTP route for full results.",
            }
        except Exception as e:
            return {
                "name": name,
                "status": "NONE_CHANNEL",
                "frame": "unresolved",
                "rows": [],
                "value": None,
                "reason": str(e),
                "instruction": "Do not invent an answer.",
            }

    return {
        "name": name,
        "status": "NONE_CHANNEL",
        "frame": "unresolved",
        "rows": [],
        "value": None,
        "reason": f"unknown tool: {name}",
        "instruction": "Do not invent an answer.",
    }
