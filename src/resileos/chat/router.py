"""Five-class chat router.

Decision order matches docs/320-titanos/chat-router.md:

1. teach cue → HUB_LEARN (writes ``user:<id>``; ``remember <s> <r> <o>`` is a world fact)
2. hub-scoped question → HUB_RECALL
3. world / store fact → TOOL_FACT
4. follow-up after an empty result → ABSTAIN_SURFACE
5. anything else → SOFT_CHAT

Learn and recall call Titanos ``learn`` / ``ask_list`` (and ``resileos_ask``,
which is ask_list). They do not reimplement binding.

Persona prose requires Metis ``allow_mouth``. On TOOL_FACT the mouth may
paraphrase only the returned rows and the declared subject/relation. A
closed mouth still returns those rows as data, and still states that the
store returned nothing — that fixed line is the abstain contract, not a
persona.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _ROOT / "scripts"
for _path in (_ROOT, _SCRIPTS):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from resileos.answer.tool_execute import execute_tool
from resileos.answer.user_profile import PERSONA_PACKS
from resileos.chat.ledger import HUB_RELATIONS, user_subject
from titanos import parse_query

CLASSES = (
    "TOOL_FACT",
    "HUB_LEARN",
    "HUB_RECALL",
    "SOFT_CHAT",
    "ABSTAIN_SURFACE",
)

_SETTING_KEYS = {"setting", "theme", "language", "timezone", "locale"}

_FACT_PHRASE = re.compile(
    r"(?i)\b(?:who is|what is|what are|when is|when did|when was|where is|which|whose)\b"
)
_HUB_CUE = re.compile(
    r"(?i)(?:"
    r"\bwhat do i\b|"
    r"\bwhat are my\b|"
    r"\bin my workspace\b|"
    r"\bmy (?:preference|preferences|settings|notes)\b|"
    r"\bdo you remember\b|"
    r"\bwhat did i tell you\b|"
    r"\babout me\b|"
    r"\b(?:user|world|org):[a-z0-9_]{1,64}\b"
    r")"
)
_SCOPED = re.compile(r"(?i)\b(user|world|org):([a-z0-9_]{1,64})\b")
_WHAT_OF = re.compile(r"(?i)\bwhat is the (\w+) of (\w+)\b")
_WHO_OF = re.compile(r"(?i)\bwho is the (\w+) of (\w+)\b")
_POSSESSIVE = re.compile(r"(?i)\b(?:who|what) is (\w+)'s (\w+)\b")

_ABSTAIN_TEXT = (
    'The Oracle has no channel and no rows for that. '
    'Say "remember that…" to teach me.'
)
_EMPTY_TEXT = "I don't have a verified fact for that in the store. No rows were returned."

_SOFT_PROSE = {
    "honest": "I'm here. I won't assert a stored fact on this turn.",
    "guide": "We can talk this through. I won't treat this turn as a stored fact.",
    "builder": "Say the next step. This turn adds no fact.",
    "mythic": "I hear you. No unstored claim leaves this turn.",
}


@dataclass
class Turn:
    text: str
    last_tool_empty: bool = False
    force_class: str | None = None
    allow_mouth: bool | None = None
    persona: str = "honest"


def _as_turn(turn: Turn | str | Mapping[str, Any]) -> Turn:
    if isinstance(turn, Turn):
        return turn
    if isinstance(turn, str):
        return Turn(text=turn)
    if isinstance(turn, Mapping):
        allow = turn["allow_mouth"] if "allow_mouth" in turn else None
        force = turn.get("force_class")
        return Turn(
            text=str(turn.get("text") or ""),
            last_tool_empty=bool(turn.get("last_tool_empty") or False),
            force_class=str(force) if force else None,
            allow_mouth=None if allow is None else bool(allow),
            persona=str(turn.get("persona") or "honest"),
        )
    raise TypeError("turn must be a str, Turn, or mapping")


def _obj(text: str, *, lower: bool = False) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().strip(" .\"'")
    cleaned = cleaned[:200]
    return cleaned.lower() if lower else cleaned


def teach_cue(text: str) -> bool:
    low = text.lower().strip()
    if re.match(r"^(?:remember|learn)\b", low):
        return True
    if "remember that" in low:
        return True
    if re.search(r"(?:^|[\n.!?,;]\s*)i prefer\b", low) and not re.search(
        r"\b(?:what|which|did)\b.{0,24}\bi prefer\b", low
    ):
        return True
    if re.search(r"\bmy [a-z0-9_]{1,32} is\b", low):
        return True
    return False


def hub_cue(text: str) -> bool:
    return _HUB_CUE.search(text) is not None


def _names(mapping: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in mapping or {}:
        out.setdefault(str(key).lower(), str(key))
    return out


def fact_cue(text: str, titanos: Any) -> bool:
    """Empirical when the wording asks a fact, or a stored name is present.

    ``parse_query`` treats any two words as ``subject relation``. That is
    used once a turn is already ``TOOL_FACT``. It is not itself a cue, or
    every greeting would hit the store.
    """
    if _FACT_PHRASE.search(text):
        return True
    entities = _names(getattr(titanos, "entities", {}) or {})
    relations = _names(getattr(titanos, "relations", {}) or {})
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text):
        if token.lower() in entities or token.lower() in relations:
            return True
    return False


def classify(text: str, titanos: Any, *, last_tool_empty: bool = False) -> str:
    """First match wins. See the module docstring for the order."""
    if teach_cue(text):
        return "HUB_LEARN"
    if hub_cue(text):
        return "HUB_RECALL"
    if fact_cue(text, titanos):
        return "TOOL_FACT"
    if last_tool_empty:
        return "ABSTAIN_SURFACE"
    return "SOFT_CHAT"


def parse_teach(text: str) -> tuple[str, str]:
    """Map a teach utterance onto ``(relation, obj)`` under the user subject."""
    raw = text.strip()
    low = raw.lower()
    prefer = re.search(r"\bi prefer\s+(.+)$", raw, re.I)
    if prefer and not re.search(r"\b(?:what|which|did)\b.{0,24}\bi prefer\b", low):
        return "prefers", _obj(prefer.group(1), lower=True)
    mine = re.search(r"\bmy\s+([a-z0-9_]{1,32})\s+is\s+(.+)$", raw, re.I)
    if mine:
        key = mine.group(1).lower()
        val = _obj(mine.group(2))
        if key in _SETTING_KEYS:
            obj = val if key == "setting" else f"{key}={val}"
            return "setting", obj
        return "stated", f"{key}={val}"
    remembered = re.search(r"^(?:remember|learn)\b[:\-]?\s*(?:that\s+)?(.+)$", raw, re.I)
    if remembered:
        rest = remembered.group(1).strip()
        parts = rest.split()
        if len(parts) >= 2 and parts[0].lower() in HUB_RELATIONS:
            return parts[0].lower(), _obj(" ".join(parts[1:]), lower=parts[0].lower() == "prefers")
        if len(parts) >= 3 and parts[1].lower() in HUB_RELATIONS:
            return parts[1].lower(), _obj(" ".join(parts[2:]), lower=parts[1].lower() == "prefers")
        nested = re.search(r"\bi prefer\s+(.+)$", rest, re.I)
        if nested:
            return "prefers", _obj(nested.group(1), lower=True)
        return "note", _obj(rest)
    return "note", _obj(raw)


_WORLD_TEACH = re.compile(
    r"^(?:remember|learn)\s+(?!that\b)(\S+)\s+(\S+)\s+(.+)$",
    re.I,
)


def parse_world_teach(text: str) -> tuple[str, str, str] | None:
    """``remember alice works_at acme`` is a world triple, not a hub note."""
    match = _WORLD_TEACH.match(text.strip())
    if not match:
        return None
    subject, relation, obj = match.group(1), match.group(2), _obj(match.group(3))
    if not subject or not relation or not obj:
        return None
    if subject.lower() in {"that", "i", "my", "me"}:
        return None
    if relation.lower() in HUB_RELATIONS:
        return None
    return subject, relation, obj


def _canon(token: str, names: dict[str, str]) -> str:
    return names.get(token.lower(), token)


def resolve_fact(text: str, titanos: Any) -> tuple[str, str, bool]:
    """Return ``(subject, relation, inverse)``. Empty strings if unresolved."""
    entities = _names(getattr(titanos, "entities", {}) or {})
    relations = _names(getattr(titanos, "relations", {}) or {})
    what = _WHAT_OF.search(text)
    if what:
        return _canon(what.group(2), entities), _canon(what.group(1), relations), False
    who = _WHO_OF.search(text)
    if who:
        return _canon(who.group(2), entities), _canon(who.group(1), relations), True
    possessive = _POSSESSIVE.search(text)
    if possessive:
        return (
            _canon(possessive.group(1), entities),
            _canon(possessive.group(2), relations),
            False,
        )
    try:
        parsed = parse_query(text.strip())
    except Exception:
        parsed = None
    if parsed:
        subject, relation, inverse = parsed
        return _canon(str(subject), entities), _canon(str(relation), relations), bool(inverse)
    found_entity = ""
    found_relation = ""
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text):
        low = token.lower()
        if not found_entity and low in entities:
            found_entity = entities[low]
        if not found_relation and low in relations:
            found_relation = relations[low]
    return found_entity, found_relation, False


def _scoped_subject(text: str, hub_id: str) -> str:
    match = _SCOPED.search(text)
    if match:
        return f"{match.group(1).lower()}:{match.group(2).lower()}"
    return user_subject(hub_id)


def _recall_relations(text: str) -> list[str]:
    low = text.lower()
    if "prefer" in low:
        return ["prefers"]
    if "setting" in low or "workspace" in low:
        return ["setting"]
    if re.search(r"\bnotes?\b", low):
        return ["note"]
    if re.search(r"\bstated\b", low):
        return ["stated"]
    return list(HUB_RELATIONS)


def mouth_open(turn: Turn) -> bool:
    """Prose is allowed only when this turn says so, or Metis allow_mouth is set.

    An explicit ``Turn.allow_mouth`` is for tests. The HTTP route leaves it
    unset and reads the last Metis policy, which defaults to closed.
    """
    if turn.allow_mouth is not None:
        return bool(turn.allow_mouth)
    from resileos.kin.wiring import mouth_allowed_from_last_cycle

    return mouth_allowed_from_last_cycle(default=False)


def _persona(name: str) -> str:
    if name in PERSONA_PACKS:
        return name
    return "honest"


def _paraphrase(subject: str, relation: str, rows: list[Any], allow: bool) -> str:
    shown = [str(row) for row in rows]
    if not shown:
        return _EMPTY_TEXT
    if allow:
        return f"{subject} {relation} {', '.join(shown)}."
    return ", ".join(shown)


def _conflict(titanos: Any, subject: str, relation: str, inverse: bool) -> bool:
    checker = getattr(titanos, "_explicit_temporal_conflict", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(subject, relation, inverse))
    except Exception:
        return False


def _ask(titanos: Any, subject: str, relation: str, inverse: bool) -> dict[str, Any]:
    if not subject or not relation:
        return execute_tool(
            "resileos_ask",
            {"subject": subject, "relation": relation, "inverse": inverse},
            titanos=titanos,
        )
    result = execute_tool(
        "resileos_ask",
        {"subject": subject, "relation": relation, "inverse": inverse},
        titanos=titanos,
    )
    rows = list(result.get("rows") or [])
    tool_status = str(result.get("status") or "")
    if tool_status == "ABSTAINED":
        status = "ABSTAINED"
    elif not rows or tool_status in {"NO_ROWS", "NONE_CHANNEL"}:
        status = "NO_ROWS"
    elif _conflict(titanos, subject, relation, inverse):
        status = "CONFLICT"
    else:
        status = "ACCEPTED"
    result["rows"] = rows
    result["router_status"] = status
    return result


def _action(
    klass: str,
    action: str,
    *,
    tool: str | None,
    subject: str,
    relation: str | None,
    relations: list[str],
    obj: str | None,
    rows: list[Any],
    wrote: bool,
    inverse: bool = False,
) -> dict[str, Any]:
    return {
        "class": klass,
        "action": action,
        "tool": tool,
        "subject": subject,
        "relation": relation,
        "relations": relations,
        "obj": obj,
        "rows": list(rows),
        "wrote": wrote,
        "inverse": inverse,
    }


def present(status: str, action: Mapping[str, Any]) -> dict[str, Any]:
    """UI flags. Status chips are only conflict, abstained, and no rows."""
    chip = {"CONFLICT": "conflict", "ABSTAINED": "abstained", "NO_ROWS": "no_rows"}.get(status)
    if status == "ACCEPTED":
        chip = None
    klass = str(action.get("class") or "")
    wrote = bool(action.get("wrote"))
    return {
        "chip": chip,
        "memory_chip": bool(wrote and status == "ACCEPTED"),
        "teach_affordance": bool(klass == "ABSTAIN_SURFACE" or chip in {"abstained", "no_rows"}),
    }


def dispatch(
    turn: Turn | str | Mapping[str, Any],
    titanos: Any,
    hub_id: str,
) -> tuple[str, str, dict[str, Any]]:
    """Return ``(reply_text, status, action_taken)``."""
    item = _as_turn(turn)
    text = item.text.strip()
    if not text:
        raise ValueError("turn text is empty")
    force = (item.force_class or "").strip() or None
    if force is not None and force not in CLASSES:
        raise ValueError(f"unknown class {force}")
    klass = force or classify(text, titanos, last_tool_empty=item.last_tool_empty)
    allow = mouth_open(item)
    persona = _persona(item.persona)
    subject = user_subject(hub_id)

    if klass == "HUB_LEARN":
        world = parse_world_teach(text)
        if world:
            fact_subject, relation, obj = world
            titanos.learn(fact_subject, relation, obj)
            rows = [str(row) for row in titanos.ask_list(fact_subject, relation)]
            wrote = obj in rows
            status = "ACCEPTED" if wrote else "NO_ROWS"
            reply = (
                f"Remembered {fact_subject} {relation} {obj}."
                if allow
                else f"{fact_subject} {relation} {obj}"
            )
            if not wrote:
                reply = _EMPTY_TEXT
            action = _action(
                "TOOL_FACT",
                "learn",
                tool="learn",
                subject=fact_subject,
                relation=relation,
                relations=[relation],
                obj=obj,
                rows=rows if wrote else [],
                wrote=wrote,
            )
            return reply, status, action
        relation, obj = parse_teach(text)
        if relation not in HUB_RELATIONS or not obj:
            action = _action(
                "HUB_LEARN",
                "learn",
                tool=None,
                subject=subject,
                relation=relation or None,
                relations=[relation] if relation else [],
                obj=obj or None,
                rows=[],
                wrote=False,
            )
            return _EMPTY_TEXT, "NO_ROWS", action
        titanos.learn(subject, relation, obj)
        rows = [str(row) for row in titanos.ask_list(subject, relation)]
        wrote = obj in rows
        status = "ACCEPTED" if wrote else "NO_ROWS"
        reply = f"Remembered {subject} {relation} {obj}." if allow else f"{subject} {relation} {obj}"
        if not wrote:
            reply = _EMPTY_TEXT
        action = _action(
            "HUB_LEARN",
            "learn",
            tool="learn",
            subject=subject,
            relation=relation,
            relations=[relation],
            obj=obj,
            rows=rows if wrote else [],
            wrote=wrote,
        )
        return reply, status, action

    if klass == "HUB_RECALL":
        subject = _scoped_subject(text, hub_id)
        relations = _recall_relations(text)
        pieces: list[str] = []
        rows: list[Any] = []
        status = "NO_ROWS"
        for relation in relations:
            result = _ask(titanos, subject, relation, False)
            got = list(result.get("rows") or [])
            part_status = str(result.get("router_status") or "NO_ROWS")
            if part_status == "CONFLICT":
                status = "CONFLICT"
            elif got and status != "CONFLICT":
                status = "ACCEPTED"
            elif part_status == "ABSTAINED" and status == "NO_ROWS":
                status = "ABSTAINED"
            if got:
                pieces.append(_paraphrase(subject, relation, got, allow))
                rows.extend(got)
        if not pieces:
            reply = _ABSTAIN_TEXT if status == "ABSTAINED" else _EMPTY_TEXT
        else:
            reply = " ".join(pieces)
        action = _action(
            "HUB_RECALL",
            "ask",
            tool="resileos_ask",
            subject=subject,
            relation=relations[0] if len(relations) == 1 else None,
            relations=relations,
            obj=None,
            rows=rows,
            wrote=False,
        )
        return reply, status, action

    if klass == "TOOL_FACT":
        fact_subject, relation, inverse = resolve_fact(text, titanos)
        result = _ask(titanos, fact_subject, relation, inverse)
        rows = list(result.get("rows") or [])
        status = str(result.get("router_status") or "NO_ROWS")
        if status == "ABSTAINED":
            reply = _ABSTAIN_TEXT
        elif not rows:
            reply = _EMPTY_TEXT
        else:
            reply = _paraphrase(fact_subject, relation, rows, allow)
        action = _action(
            "TOOL_FACT",
            "ask",
            tool="resileos_ask",
            subject=fact_subject,
            relation=relation or None,
            relations=[relation] if relation else [],
            obj=None,
            rows=rows,
            wrote=False,
            inverse=inverse,
        )
        return reply, status, action

    if klass == "ABSTAIN_SURFACE":
        action = _action(
            "ABSTAIN_SURFACE",
            "abstain",
            tool=None,
            subject=subject,
            relation=None,
            relations=[],
            obj=None,
            rows=[],
            wrote=False,
        )
        return _ABSTAIN_TEXT, "ABSTAINED", action

    action = _action(
        "SOFT_CHAT",
        "none",
        tool=None,
        subject=subject,
        relation=None,
        relations=[],
        obj=None,
        rows=[],
        wrote=False,
    )
    if not allow:
        return "", "MOUTH_CLOSED", action
    return _SOFT_PROSE[persona], "ACCEPTED", action
