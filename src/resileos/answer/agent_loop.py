"""Studio chat loop: five-class router, explicit tools, and a bounded Kin cycle.

Ordinary turns keep history under a Hermes budget and run one Kin cycle.
``/search`` and ``/tool`` stay explicit tool use. Assertive mouth waits on
a verified cycle or the Metis allow_mouth policy. An unverified cycle does
not learn.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from resileos.chat import turn_cycle
from resileos.chat.ledger import normalize_hub_id
from resileos.chat.router import Turn, dispatch, present
from resileos.harness.legions.search import web_search
from resileos.harness.surface import ALWAYS_VISIBLE_TOOLS, DEMIGOD_TOOLS

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
    src = _source_for(action, source)
    verified = status == "ACCEPTED" and klass in _FACT_CLASSES
    if klass == "SOFT_CHAT" or src == "conversational":
        verified = False
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
        "allow_mouth": False,
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


def conversational_reply(text: str, persona: str, intent: str) -> str:
    """A line that varies with the turn and does not assert a stored fact."""
    from resileos.answer.user_profile import PERSONA_PACKS

    name = persona if persona in PERSONA_PACKS else "honest"
    pack = PERSONA_PACKS[name]
    words = (text or "").strip().split()
    lead = words[0] if words else "hello"
    if intent == "greeting":
        heard = " ".join(words[:4]) or lead
        return f"{pack['label']}. {heard}. This is not a stored fact."
    if intent == "smalltalk":
        heard = " ".join(words[:6])
        return f"{pack['label']} ({pack['tone']}): {heard}. I will not assert a stored fact."
    if intent == "meta":
        return (
            f"I am {pack['label']}. I keep exact rows, derive only from those rows, "
            "and abstain when a row is missing."
        )
    clip = " ".join(words[:8])[:80]
    return f"I heard “{clip}”. That line states no stored fact."


def _fast_reply(
    text: str,
    intent: str,
    persona: str,
    hub_id: str,
    window: list[dict[str, Any]],
    budget: Any,
) -> dict[str, Any]:
    """Persona mouth only. Skips Themis, Momus, Atlas, and the Kin cycle."""
    from resileos.chat.deferred_review import schedule_review

    reply = conversational_reply(text, persona, intent)
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
    body = present_chat(
        reply,
        "ACCEPTED",
        action,
        hub_id=hub_id,
        persona=persona,
        source="conversational",
    )
    body["verified"] = False
    body["evidence"] = []
    body["intent"] = intent
    body["checks_skipped"] = ["themis", "momus", "atlas"]
    body["factual_mouth"] = False
    schedule_review(lambda: _post_fast_review(reply))
    body["review"] = "deferred"
    try:
        from resileos.chat.turn_cycle import COMPANION_INTRO
        from resileos.kin.aphrodite import get_store

        stage = int(get_store().get(hub_id).tutorial_stage)
    except Exception:
        stage = 0
    finished = _finish(body, window, None, assertive=False, budget=budget)
    finished["verified"] = False
    finished["cycle_verified"] = False
    finished["mouth_open"] = True
    finished["factual_mouth"] = False
    finished["evidence"] = []
    if stage == 0:
        finished["companion_prompt"] = COMPANION_INTRO
    return finished


def _post_fast_review(reply: str) -> dict[str, Any]:
    from resileos.harness.packet import ControlPacket
    from resileos.harness.separated import Proposal, Verdict, zeus_head

    learned: list[tuple[str, str, str]] = []

    def learn(subject: str, relation: str, obj: str) -> None:
        learned.append((subject, relation, obj))

    packet = ControlPacket(id="chat-fast")
    proposal = Proposal(
        id=packet.id,
        writer="mouth",
        action_type="learn",
        result={"status": "conversational"},
        claims=[],
        packet=packet,
    )

    def reject(item: Proposal) -> Verdict:
        return Verdict(item.id, "fast-path", False, "conversational reply is not a fact", [])

    head = zeus_head(proposal, [("fast-path", reject)], learn)
    head["learned"] = learned
    return head


def _finish(
    body: dict[str, Any],
    window: list[dict[str, Any]],
    cycle: dict[str, Any] | None,
    *,
    assertive: bool,
    budget: Any = None,
) -> dict[str, Any]:
    action = body.get("action_taken") or {}
    body.setdefault("factual_mouth", False)
    body.setdefault(
        "structured",
        {
            "status": body.get("status"),
            "subject": action.get("subject"),
            "relation": action.get("relation"),
            "rows": list(body.get("rows") or []),
            "obj": action.get("obj"),
            "value": body.get("reply_text") or "",
        },
    )
    return turn_cycle.attach_turn_fields(
        body,
        window=window,
        cycle=cycle,
        assertive=assertive,
        budget=budget,
    )


def _row_groups(action: dict[str, Any], titanos: Any) -> list[tuple[str, list[str]]] | None:
    relations = [str(item) for item in (action.get("relations") or []) if item]
    subject = str(action.get("subject") or "")
    if len(relations) <= 1 or not subject:
        return None
    ask = getattr(titanos, "ask_list", None)
    if not callable(ask):
        return None
    groups: list[tuple[str, list[str]]] = []
    for relation in relations:
        got = [str(row) for row in ask(subject, relation) or []]
        if got:
            groups.append((relation, got))
    return groups or None


def _persona_reply(
    reply: str,
    status: str,
    action: dict[str, Any],
    *,
    persona: str,
    hub_id: str,
    verified: bool,
    allow_mouth: bool,
    prose: bool,
    titanos: Any,
) -> dict[str, Any]:
    """Persona sentence over the structured turn. Failures keep ``reply``."""
    from resileos.chat.persona_mouth import (
        budgeted_lessons,
        remember_verified_learn,
        render_persona_mouth,
    )

    if (
        verified
        and action.get("wrote")
        and status == "ACCEPTED"
        and action.get("subject")
        and action.get("relation")
        and action.get("obj")
    ):
        try:
            remember_verified_learn(
                hub_id,
                str(action["subject"]),
                str(action["relation"]),
                str(action["obj"]),
            )
        except Exception:
            log.exception("verified learn lesson was not recorded")
    lessons: list[str] = []
    if prose and verified:
        try:
            lessons = budgeted_lessons(hub_id)
        except Exception:
            log.exception("hades lessons were not loaded")
            lessons = []
    try:
        groups = _row_groups(action, titanos)
    except Exception:
        groups = None
    try:
        return render_persona_mouth(
            status=status,
            persona=persona,
            subject=str(action.get("subject") or ""),
            relation=action.get("relation"),
            rows=list(action.get("rows") or []),
            obj=action.get("obj"),
            wrote=bool(action.get("wrote")),
            router_class=str(action.get("class") or ""),
            action_name=str(action.get("action") or ""),
            verified=verified,
            allow_mouth=allow_mouth,
            prose=prose,
            lessons=lessons,
            hub_id=hub_id,
            prior_reply=reply,
            groups=groups,
        )
    except Exception:
        log.exception("persona mouth failed")
        return {
            "apply": False,
            "factual": False,
            "structured": {
                "status": status,
                "subject": action.get("subject"),
                "relation": action.get("relation"),
                "rows": list(action.get("rows") or []),
                "obj": action.get("obj"),
                "value": reply,
            },
            "audit": {"rendered": False, "writes_residual": False},
            "lessons": lessons,
        }


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
    prose: bool = True,
) -> dict[str, Any]:
    """Route one studio turn through retrieval, and a Kin cycle when it is chat.

    ``prose`` asks for a persona sentence when the gate allows it. It does
    not open the factual mouth on an unverified cycle.
    """
    window = turn_cycle.budget_history(history)
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
        return _finish(body, window, None, assertive=False)

    if text.lower().startswith("/search "):
        body = await _maybe_search(text[8:].strip())
        return _finish(body, window, None, assertive=False)
    if text.lower() == "/search":
        body = await _maybe_search("")
        return _finish(body, window, None, assertive=False)

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
            body = present_chat(
                "Name a tool after /tool.",
                "NO_ROWS",
                action,
                hub_id=hub_id,
                persona=persona,
                source="tool",
            )
            return _finish(body, window, None, assertive=False)
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
        return _finish(body, window, None, assertive=False)

    if not text:
        raise ValueError("turn text is empty")

    from resileos.kin.iris import FAST_INTENTS, classify_intent
    from resileos.kin.metis import hermes_budget_for

    from resileos.chat.router import parse_preference

    intent = classify_intent(text, titanos=titanos)
    budget = hermes_budget_for(text)
    window = turn_cycle.budget_history(
        history,
        max_items=budget.max_items,
        max_depth=budget.max_depth,
    )
    # A preference still goes through the router. A follow-up after an
    # empty tool result still abstains. Neither one is a fast greeting.
    forced = bool((force_class or "").strip())
    if (
        intent in FAST_INTENTS
        and parse_preference(text) is None
        and not last_tool_empty
        and not forced
    ):
        return _fast_reply(text, intent, persona, hub_id, window, budget)

    try:
        cycle = turn_cycle.run_bounded_cycle(text, window, hub_id, titanos)
    except Exception:
        log.exception("bounded kin cycle failed")
        cycle = {
            "verified": False,
            "allow_mouth": False,
            "tutorial_fragment": None,
            "checkpoint": None,
            "reason": "cycle failed",
            "packet_hash": "",
            "stage_before": 0,
            "history_used": len(window),
            "legions": {},
        }
    spoken = turn_cycle.continuation_text(text, window, titanos)
    empty_follow = turn_cycle.infer_last_tool_empty(window, last_tool_empty)
    # The client request is necessary. Verification or Metis still decides.
    assertive = bool(prose and (cycle.get("verified") or cycle.get("allow_mouth")))
    triple = None
    try:
        triple = turn_cycle.writable_triple(spoken, hub_id, force_class)
    except ValueError:
        triple = None

    if triple is not None and not cycle.get("verified"):
        action = {
            "class": "HUB_LEARN",
            "action": "learn",
            "tool": None,
            "subject": triple[0],
            "relation": triple[1],
            "relations": [triple[1]],
            "obj": triple[2],
            "rows": [],
            "wrote": False,
            "inverse": False,
        }
        body = present_chat(
            turn_cycle.UNVERIFIED_WRITE,
            "ABSTAINED",
            action,
            hub_id=hub_id,
            persona=persona,
        )
        body["verified"] = False
        return _finish(body, window, cycle, assertive=False, budget=budget)

    store = titanos
    if triple is not None and cycle.get("verified"):
        head = turn_cycle.zeus_learn(titanos, triple)
        if not head.get("applied"):
            reason = str(head.get("reason") or "not approved")[:180]
            action = {
                "class": "HUB_LEARN",
                "action": "learn",
                "tool": None,
                "subject": triple[0],
                "relation": triple[1],
                "relations": [triple[1]],
                "obj": triple[2],
                "rows": [],
                "wrote": False,
                "inverse": False,
            }
            reply = (
                "Nothing was stored. "
                f"{reason}. "
                'Teach a clear "remember …" line, attach a document, or ask a fact already in the store.'
            )
            body = present_chat(reply, "ABSTAINED", action, hub_id=hub_id, persona=persona)
            body["verified"] = False
            return _finish(body, window, cycle, assertive=assertive, budget=budget)
        store = turn_cycle.LearnProxy(titanos)

    try:
        reply, status, action = dispatch(
            Turn(
                text=spoken,
                last_tool_empty=empty_follow,
                force_class=force_class,
                allow_mouth=assertive,
                persona=persona,
            ),
            store,
            hub_id,
        )
    except ValueError:
        raise
    except Exception:
        log.exception("chat dispatch failed")
        raise

    if not reply and status == "MOUTH_CLOSED" and prose:
        reply = turn_cycle.orientation_text(persona)
    prior_reply = reply
    rendered = _persona_reply(
        reply,
        status,
        action,
        persona=persona,
        hub_id=hub_id,
        verified=bool(cycle.get("verified")),
        allow_mouth=bool(cycle.get("allow_mouth")),
        prose=prose,
        titanos=store,
    )
    if rendered.get("apply"):
        reply = str(rendered.get("text") or reply)
    body = present_chat(reply, status, action, hub_id=hub_id, persona=persona)
    body["structured"] = rendered.get("structured") or {
        "status": status,
        "subject": action.get("subject"),
        "relation": action.get("relation"),
        "rows": list(action.get("rows") or []),
        "obj": action.get("obj"),
        "value": prior_reply,
    }
    body["factual_mouth"] = bool(rendered.get("factual"))
    body["mouth"] = rendered.get("audit") or {"rendered": False, "writes_residual": False}
    if rendered.get("lessons"):
        body["lessons"] = list(rendered["lessons"])
    if cycle.get("allow_mouth") is not None:
        body["allow_mouth"] = bool(cycle.get("allow_mouth"))
    fragment = action.get("tutorial_fragment")
    if not fragment:
        from resileos.kin.aphrodite import note_router_step

        fragment = note_router_step(hub_id, status, action)
    if not fragment and cycle.get("verified"):
        fragment = cycle.get("tutorial_fragment")
    if fragment and (status == "ACCEPTED" or status == "ABSTAINED"):
        body["tutorial_fragment"] = fragment
    if file_data:
        body["file"] = {key: value for key, value in file_data.items() if key != "bytes"}
        note = _upload_note(file_data)
        body["value"] = f"{note}\n\n{reply}".strip()
        body["reply_text"] = body["value"]
    return _finish(body, window, cycle, assertive=assertive and status != "MOUTH_CLOSED", budget=budget)
