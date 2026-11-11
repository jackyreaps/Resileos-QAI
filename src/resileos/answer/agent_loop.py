"""Studio chat loop: five-class router plus explicit search, tool, and upload paths."""
from __future__ import annotations

import inspect
import logging
from typing import Any

from resileos.chat.ledger import normalize_hub_id
from resileos.chat.router import Turn, dispatch, present
from resileos.harness.legions.search import web_search
from resileos.harness.surface import ALWAYS_VISIBLE_TOOLS, DEMIGOD_TOOLS
from resileos.kin.wiring import mouth_allowed_from_last_cycle

log = logging.getLogger(__name__)

_FACT_CLASSES = {"TOOL_FACT", "HUB_LEARN", "HUB_RECALL"}


def _source_for(action: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override
    tool = action.get("tool")
    if tool:
        return str(tool)
    klass = str(action.get("class") or "")
    if klass == "HUB_LEARN":
        return "memory"
    if klass == "SOFT_CHAT":
        return "conversational"
    if klass == "ABSTAIN_SURFACE":
        return "abstain"
    return "residual"


def present_chat(
    reply: str,
    status: str,
    action: dict[str, Any],
    *,
    hub_id: str,
    persona: str,
    source: str | None = None,
) -> dict[str, Any]:
    """HTTP body used by POST /api/v1/chat and /upload.

    Keeps the persona-surface fields (reply_text, router_class, chips) and
    aliases the studio page understands (value, source, verified).
    """
    flags = present(status, action)
    klass = str(action.get("class") or "")
    verified = status == "ACCEPTED" and klass in _FACT_CLASSES
    src = _source_for(action, source)
    tool = action.get("tool")
    tool_calls = [{"tool": tool}] if tool else []
    try:
        normalized = normalize_hub_id(hub_id)
    except ValueError:
        normalized = hub_id
    return {
        "reply_text": reply,
        "status": status,
        "action_taken": action,
        "router_class": klass or None,
        "hub_id": normalized,
        "subject": action.get("subject"),
        "rows": list(action.get("rows") or []),
        "chip": flags["chip"],
        "memory_chip": flags["memory_chip"],
        "teach_affordance": flags["teach_affordance"],
        "persona": persona,
        "allow_mouth": mouth_allowed_from_last_cycle(default=False),
        "value": reply,
        "source": src,
        "verified": verified,
        "tool_calls": tool_calls,
        "evidence": [],
    }


def _call_named_tool(name: str, payload: dict[str, Any] | None = None) -> Any:
    fn = ALWAYS_VISIBLE_TOOLS.get(name) or DEMIGOD_TOOLS.get(name)
    if fn is None:
        raise KeyError(name)
    raw = dict(payload or {})
    sig = inspect.signature(fn)
    accepts_var_kw = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
    )
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if accepts_var_kw or key in sig.parameters:
            kwargs[key] = value
    for key, param in sig.parameters.items():
        if key in kwargs:
            continue
        if param.default is not inspect.Parameter.empty:
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if key == "packet":
            kwargs[key] = {}
        elif key in {"options", "evidence", "scars"}:
            kwargs[key] = []
        elif key in {"question", "name", "query"}:
            kwargs[key] = ""
        elif key == "result":
            kwargs[key] = {}
    if inspect.iscoroutinefunction(fn):
        raise TypeError(f"{name} is async and must be awaited by the caller")
    return fn(**kwargs)


async def _maybe_search(query: str) -> dict[str, Any]:
    result = await web_search(query)
    snippets = []
    for row in result.get("results") or []:
        title = row.get("title") or ""
        snippet = row.get("snippet") or ""
        url = row.get("url") or ""
        line = " ".join(part for part in (title, snippet) if part).strip()
        if url:
            line = f"{line} ({url})" if line else url
        if line:
            snippets.append(line)
    summary = result.get("evidence_summary") or " ".join(snippets)
    if result.get("status") == "ERROR":
        text = f"Web search failed: {result.get('error') or 'unknown error'}"
        status = "NO_ROWS"
    elif not snippets:
        text = "Web search returned no rows. That is not a stored fact."
        status = "NO_ROWS"
    else:
        text = "Unverified web search results:\n" + "\n".join(f"- {item}" for item in snippets)
        if summary and summary not in text:
            text = f"{text}\n{summary}"
        status = "ACCEPTED"
    action = {
        "class": "SOFT_CHAT",
        "action": "search",
        "tool": "web_search",
        "subject": None,
        "relation": None,
        "relations": [],
        "obj": query,
        "rows": snippets,
        "wrote": False,
        "inverse": False,
    }
    body = present_chat(
        text, status, action, hub_id="anon", persona="honest", source="web_search"
    )
    body["verified"] = False
    body["search"] = {
        "query": query,
        "status": result.get("status"),
        "results": result.get("results") or [],
    }
    return body


def _upload_note(file_data: dict[str, Any]) -> str:
    name = file_data.get("name") or "file"
    kind = file_data.get("type") or "application/octet-stream"
    size = file_data.get("size")
    bits = [f"Received {name}", f"type {kind}"]
    if size is not None:
        bits.append(f"{size} bytes")
    if file_data.get("width") and file_data.get("height"):
        bits.append(f"{file_data['width']}×{file_data['height']}")
    return (
        f"{', '.join(bits)}. Not learned as a fact. "
        'Send a "remember …" line if you want the store to keep something about it.'
    )


async def run_agent_chat(
    titanos: Any,
    message: str,
    history: list[dict] | None = None,
    file_data: dict[str, Any] | None = None,
    *,
    hub_id: str = "anon",
    force_class: str | None = None,
    last_tool_empty: bool = False,
    persona: str = "honest",
) -> dict[str, Any]:
    """Route one studio turn. History is accepted and unused by the router."""
    del history
    text = (message or "").strip()

    if file_data and not text:
        action = {
            "class": "SOFT_CHAT",
            "action": "none",
            "tool": None,
            "subject": file_data.get("subject"),
            "relation": None,
            "relations": [],
            "obj": file_data.get("name"),
            "rows": [],
            "wrote": False,
            "inverse": False,
        }
        body = present_chat(
            _upload_note(file_data),
            "ACCEPTED",
            action,
            hub_id=hub_id,
            persona=persona,
            source="upload",
        )
        body["verified"] = False
        body["file"] = {key: value for key, value in file_data.items() if key != "bytes"}
        return body

    if text.lower().startswith("/search "):
        return await _maybe_search(text[8:].strip())
    if text.lower() == "/search":
        return await _maybe_search("")

    if text.lower().startswith("/tool "):
        name = text[6:].strip().split()[0] if text[6:].strip() else ""
        if not name:
            action = {
                "class": "SOFT_CHAT",
                "action": "none",
                "tool": None,
                "subject": None,
                "relation": None,
                "relations": [],
                "obj": None,
                "rows": [],
                "wrote": False,
                "inverse": False,
            }
            return present_chat(
                "Name a tool after /tool.",
                "NO_ROWS",
                action,
                hub_id=hub_id,
                persona=persona,
                source="tool",
            )
        try:
            raw = _call_named_tool(name, {})
            import json

            rendered = json.dumps(raw, indent=2, default=str)
            status = "ACCEPTED"
        except KeyError:
            raw = {"detail": f"unknown tool: {name}"}
            rendered = f"Unknown tool: {name}"
            status = "NO_ROWS"
        except Exception as exc:
            raw = {"detail": str(exc)}
            rendered = f"Tool {name} failed: {exc}"
            status = "NO_ROWS"
        action = {
            "class": "SOFT_CHAT",
            "action": "none",
            "tool": name,
            "subject": None,
            "relation": None,
            "relations": [],
            "obj": None,
            "rows": [],
            "wrote": False,
            "inverse": False,
        }
        body = present_chat(
            rendered, status, action, hub_id=hub_id, persona=persona, source="tool"
        )
        body["verified"] = False
        body["tool_result"] = raw
        return body

    if not text:
        raise ValueError("turn text is empty")

    try:
        reply, status, action = dispatch(
            Turn(
                text=text,
                last_tool_empty=last_tool_empty,
                force_class=force_class,
                allow_mouth=None,
                persona=persona,
            ),
            titanos,
            hub_id,
        )
    except ValueError:
        raise
    except Exception:
        log.exception("chat dispatch failed")
        raise

    body = present_chat(reply, status, action, hub_id=hub_id, persona=persona)
    if file_data:
        body["file"] = {key: value for key, value in file_data.items() if key != "bytes"}
        body["value"] = f"{_upload_note(file_data)}\n\n{reply}".strip()
        body["reply_text"] = body["value"]
    return body
