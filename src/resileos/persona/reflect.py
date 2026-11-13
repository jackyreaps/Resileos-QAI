"""Read the persona store for the mouth and the tutorial.

User cells stay labeled ``user-stated``. Seed cells stay ``verified-seed``.
An unknown user fact is an abstain. Nothing here calls ``learn``.
"""
from __future__ import annotations

import re

from resileos.persona.principal import (
    PersonaError,
    principal_from_chat_key,
    resolve_principal,
)
from resileos.persona.reflection import individual_frame, latent_frame
from resileos.persona.seed import LABEL_SEED
from resileos.persona.store import LABEL_USER, get_persona_store

_NAME = re.compile(r"(?i)\b(?:what is my name|what(?:'s| is) my name|who am i)\b")
_GOAL = re.compile(r"(?i)\bwhat(?:'s| is) my goal\b")
_SKILL = re.compile(r"(?i)\bwhat(?:'s| is) my skill(?: level)?\b")
_ABOUT = re.compile(r"(?i)\bwhat do you know about me\b")
_CAN = re.compile(r"(?i)\b(?:what can you do|who are you|what are you)\b")
_LIMITS = re.compile(r"(?i)\bwhat are your limits\b")
_KEYS = re.compile(r"(?i)\bhow do i (?:sign in|get a key)\b")
_NEXT = re.compile(r"(?i)\b(?:what(?:'s| is) the next step|tutorial)\b")

_ABSTAIN = "I do not have a user-stated fact for that."


def _packet_base() -> dict:
    return {
        "tier": "individual",
        "flow": ["individual", "hub", "latent"],
        "opt_in_required": True,
        "writes_titanos": False,
        "writes_residual_core": False,
        "gnosis": "unfilled",
        "latent_hub": "persona-residual",
        "self": [],
        "user": [],
        "residual": [],
        "tutorial": {"next": None, "completed": []},
        "abstain": False,
        "principal": None,
    }


def recall_packet(chat_key: str | None) -> dict:
    """Self-facts plus this individual's stated facts. Safe for anon."""
    packet = _packet_base()
    try:
        store = get_persona_store()
        seed = store.seed()
    except PersonaError as exc:
        packet["abstain"] = True
        packet["reason"] = str(exc)
        return packet
    packet["self"] = seed.public_rows()
    packet["seed_version"] = seed.version
    principal = principal_from_chat_key(chat_key)
    completed: list[str] = []
    if principal is not None:
        packet["principal"] = principal.to_dict()
        try:
            stated = store.list_stated(principal)
            residual = store.list_residual(principal)
        except PersonaError as exc:
            packet["abstain"] = True
            packet["reason"] = str(exc)
            stated = []
            residual = []
        packet["user"] = stated
        packet["residual"] = residual
        for cell in stated:
            slot = str(cell.get("id") or "")
            if slot.startswith("progress_") and cell.get("text") == "done":
                completed.append(slot[len("progress_") :])
    try:
        nxt = _next_step(store, completed)
    except PersonaError:
        nxt = None
    packet["tutorial"] = {"next": nxt, "completed": completed}
    if principal is None:
        packet["frame"] = latent_frame().to_dict()
    else:
        try:
            packet["frame"] = store.load_individual(principal).frame
        except PersonaError:
            packet["frame"] = individual_frame(principal.id).to_dict()
    return packet


def _next_step(store, completed: list[str]) -> dict | None:
    done = set(completed)
    for row in store.seed().tutorial_rows():
        if row["id"] not in done:
            return row
    return None


def record_tutorial_fragment(chat_key: str | None, fragment: str) -> dict | None:
    principal = principal_from_chat_key(chat_key)
    if principal is None or not fragment:
        return None
    store = get_persona_store()
    step = store.seed().step_for_fragment(fragment)
    if step is None:
        return None
    return store.record_tutorial(principal, step["id"])


def reflect_utterance(utterance: str, chat_key: str | None) -> dict | None:
    """Answer a reflection question from the store, or abstain."""
    text = (utterance or "").strip()
    if not text:
        return None
    store = get_persona_store()
    seed = store.seed()
    if _CAN.search(text):
        rows = [row for row in seed.public_rows() if row["topic"] == "capability"]
        spoken = " ".join(row["text"] for row in rows[:2])
        return _seed_answer(spoken or _ABSTAIN)
    if _LIMITS.search(text):
        rows = [row for row in seed.public_rows() if row["topic"] == "limit"]
        spoken = " ".join(row["text"] for row in rows[:2])
        return _seed_answer(spoken or _ABSTAIN)
    if _KEYS.search(text):
        rows = [row for row in seed.public_rows() if row["topic"] == "keys"]
        spoken = " ".join(row["text"] for row in rows[:2])
        return _seed_answer(spoken or _ABSTAIN)
    if _NEXT.search(text):
        packet = recall_packet(chat_key)
        nxt = (packet.get("tutorial") or {}).get("next")
        if not nxt:
            return _seed_answer("The tutorial steps in the seed are done.")
        return _seed_answer(str(nxt.get("text") or ""))
    kind = None
    if _NAME.search(text):
        kind = "name"
    elif _GOAL.search(text):
        kind = "goal"
    elif _SKILL.search(text):
        kind = "skill"
    elif _ABOUT.search(text):
        kind = "about"
    else:
        return None
    principal = principal_from_chat_key(chat_key)
    if principal is None:
        return _abstain()
    stated = store.list_stated(principal)
    if kind == "about":
        rows = [cell for cell in stated if cell.get("kind") != "tutorial"]
        if not rows:
            return _abstain()
        bits = [f"{cell['kind']} {cell['text']}" for cell in rows]
        return _user_answer("You stated " + "; ".join(bits) + ".")
    rows = [cell for cell in stated if cell.get("kind") == kind or cell.get("id") == kind]
    if not rows:
        return _abstain()
    return _user_answer(f"You stated {rows[0]['text']}.")


def _abstain() -> dict:
    return {
        "applies": True,
        "status": "ABSTAINED",
        "text": _ABSTAIN,
        "label": LABEL_USER,
        "known": False,
    }


def _user_answer(text: str) -> dict:
    return {
        "applies": True,
        "status": "ACCEPTED",
        "text": f"{text} That is user-stated, not a verified fact.",
        "label": LABEL_USER,
        "known": True,
    }


def _seed_answer(text: str) -> dict:
    return {
        "applies": True,
        "status": "ACCEPTED",
        "text": text,
        "label": LABEL_SEED,
        "known": True,
    }


def apply_turn_recall(body: dict, utterance: str = "") -> dict:
    """Attach recall on a chat body. Do not replace a factual mouth sentence."""
    key = str(body.get("hub_id") or "")
    fragment = body.get("tutorial_fragment")
    if fragment:
        try:
            record_tutorial_fragment(key, str(fragment))
        except PersonaError:
            pass
    try:
        packet = recall_packet(key)
        answer = reflect_utterance(utterance, key)
    except PersonaError as exc:
        body["persona_recall"] = _packet_base() | {"abstain": True, "reason": str(exc)}
        return body
    if answer is not None:
        packet["answer"] = answer
        if answer.get("applies") and not body.get("factual_mouth"):
            body["reply_text"] = answer["text"]
            body["value"] = answer["text"]
            if answer.get("status"):
                body["status"] = answer["status"]
    body["persona_recall"] = packet
    return body


def principal_for_api(
    *,
    account_id: str | None,
    session_id: str | None,
) -> Principal:
    return resolve_principal(account_id=account_id, session_id=session_id)
