"""Hook the UI can call. Writes stay in the persona store."""
from __future__ import annotations

import re

from resileos.persona.principal import PersonaError, principal_from_chat_key
from resileos.persona.store import get_persona_store

_COMMAND = re.compile(r"(?i)^persona:\s*(\S+)\s+(.+)$")
_SHARED = re.compile(r"^([a-z][a-z0-9_]{0,63})\s+(.+)$")


def persona_hook(action: str, **kwargs) -> dict:
    """``list``, ``put``, ``delete``, ``recall``, or ``promote``."""
    from resileos.persona.reflect import principal_for_api, recall_packet

    name = (action or "").strip().lower()
    store = get_persona_store()
    if name == "recall":
        key = kwargs.get("account_id") or kwargs.get("session_id") or kwargs.get("chat_key")
        return recall_packet(str(key or ""))
    principal = principal_for_api(
        account_id=kwargs.get("account_id"),
        session_id=kwargs.get("session_id"),
    )
    if name == "list":
        return {
            "principal": principal.to_dict(),
            "stated": store.list_stated(principal),
            "residual": store.list_residual(principal),
            "writes_titanos": False,
        }
    if name == "put":
        cell = store.put_stated(
            principal,
            str(kwargs.get("fact_id") or ""),
            str(kwargs.get("text") or ""),
            kind=str(kwargs.get("kind") or "stated"),
            personal=kwargs.get("personal"),
        )
        return {"fact": cell, "writes_titanos": False}
    if name == "delete":
        removed = store.delete_stated(principal, str(kwargs.get("fact_id") or ""))
        return {"deleted": removed, "writes_titanos": False}
    if name == "promote":
        target = str(kwargs.get("to") or "hub")
        opt_in = bool(kwargs.get("opt_in"))
        guild_id = str(kwargs.get("guild_id") or "")
        fact_id = str(kwargs.get("fact_id") or "")
        if target == "latent":
            return store.promote_to_latent(
                principal, guild_id, fact_id, opt_in=opt_in
            )
        if target != "hub":
            raise PersonaError("promote to hub or latent")
        return store.promote_to_hub(principal, guild_id, fact_id, opt_in=opt_in)
    raise PersonaError(f"unknown persona action {action}")


def persona_command_action(text: str, chat_key: str) -> tuple[str, str, dict]:
    """Apply ``persona: ...`` without calling learn. Returns reply, status, action."""
    match = _COMMAND.match((text or "").strip())
    action = {
        "class": "SOFT_CHAT",
        "action": "persona",
        "tool": None,
        "subject": None,
        "relation": None,
        "relations": [],
        "obj": None,
        "rows": [],
        "wrote": False,
        "inverse": False,
    }
    if match is None:
        return "Say persona: name, goal, skill, shared, or forget.", "NO_ROWS", action
    command = match.group(1).lower()
    rest = match.group(2).strip()
    principal = principal_from_chat_key(chat_key)
    if principal is None:
        return (
            "Sign in with a username to keep a fact. A signed-out session id can be sent to the persona API.",
            "ABSTAINED",
            action,
        )
    store = get_persona_store()
    try:
        if command == "forget":
            removed = store.delete_stated(principal, rest.split()[0].lower())
            reply = "Deleted that user-stated fact." if removed else "I do not have a user-stated fact for that."
            status = "ACCEPTED" if removed else "ABSTAINED"
            return reply, status, action
        if command == "shared":
            parts = _SHARED.match(rest)
            if parts is None:
                return "Say persona: shared <id> <text>.", "NO_ROWS", action
            cell = store.put_stated(
                principal,
                parts.group(1),
                parts.group(2),
                kind="shared",
                personal=False,
            )
        elif command in {"name", "goal", "skill"}:
            cell = store.put_stated(principal, command, rest, kind=command, personal=True)
        else:
            return "Say persona: name, goal, skill, shared, or forget.", "NO_ROWS", action
    except PersonaError as exc:
        return str(exc), "ABSTAINED", action
    action["obj"] = cell["id"]
    return (
        f"I will keep that you stated {cell['text']}. That stays user-stated, not a verified fact.",
        "ACCEPTED",
        action,
    )
