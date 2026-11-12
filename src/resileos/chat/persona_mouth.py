"""Persona mouth. Expands a verified structured answer into a sentence.

The residual rows stay the source of truth. This module does not call
``learn``, does not start a model, and does not add a claim that is not
in the structured answer or a verified learn-lesson. Aphrodite care
weights may color a sentence. They do not write a triple.

Factual sentences require a verified cycle. ``should_render_prose``
remains the client-request gate: ``prose`` false never renders. Metis
``allow_mouth`` may open a non-factual persona line. It does not open
an assertive fact on an unverified cycle.
"""
from __future__ import annotations

import re
from typing import Any

from resileos.answer.user_profile import PERSONA_PACKS
from resileos.chat.persona_envelope import build_envelope
from resileos.kin.frames import classify_decision
from resileos.kin.hermes import HermesBudget, make_hermes_navigator
from resileos.kin.mouth_policy import should_render_prose
from resileos.ui.custom_mouth import answer as custom_answer
from resileos.ui.custom_mouth import epistemic_label
from resileos.ui.language_codex import grammar_of, speak
from resileos.ui.language_tool import detect_language

LESSON_BUDGET = 4

_FACT_CLASSES = frozenset({"TOOL_FACT", "HUB_LEARN", "HUB_RECALL"})

_SOFT = {
    "honest": "I am here with you. Ask for a row the store already holds, or teach me one.",
    "guide": "We can do this together. Ask for a stored row, or teach me one.",
    "builder": "Say the next step. Ask a stored row, or teach one.",
    "mythic": "I am listening. Name a stored row, or teach me a line to keep.",
}

# Fixed words the templates may use. Anything else must come from the
# structured answer or a verified lesson.
_LEXICON = frozenset(
    """
    a already am and ask asking at can cannot care check checked checking
    choose conflict disagrees do does fact facts for from have here hold
    holds i in into is it keep keeping kept like line listen listening me
    more name names next not of on one only or pick preference ready record
    remember row rows said say stays step steps store stored teach tell than
    that the this through to together turn under unverified verification
    verified want we what when where which while will with you your
    """.split()
)

_TOKEN = re.compile(r"[A-Za-z0-9_']+")


def _persona(name: str) -> str:
    if name in PERSONA_PACKS:
        return name
    return "honest"


def unsupported_tokens(text: str, allowed: list[str]) -> list[str]:
    """Tokens that are neither template words nor pieces of the allowed facts."""
    allowed_tokens: set[str] = set()
    for fragment in allowed:
        for token in _TOKEN.findall(str(fragment).lower()):
            allowed_tokens.add(token)
    stray: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        if token in _LEXICON or token in allowed_tokens:
            continue
        stray.append(token)
    return stray


def _join(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + ", and " + values[-1]


def _soft_line(persona: str) -> str:
    return _SOFT[_persona(persona)]


def _fact_line(persona: str, subject: str, relation: str, shown: str) -> str:
    name = _persona(persona)
    if name == "guide":
        return f"The store holds this, and only this: {subject} {relation} {shown}."
    if name == "builder":
        return f"Stored: {subject} {relation} {shown}."
    if name == "mythic":
        return f"The record names it: {subject} {relation} {shown}."
    return f"What I have on record is that {subject} {relation} {shown}."


def _learn_line(persona: str, subject: str, relation: str, shown: str) -> str:
    name = _persona(persona)
    if name == "guide":
        return f"I checked it and stored that {subject} {relation} {shown}."
    if name == "builder":
        return f"Stored under verification: {subject} {relation} {shown}."
    if name == "mythic":
        return f"It is verified and kept: {subject} {relation} {shown}."
    return f"I verified and stored that {subject} {relation} {shown}."


def _abstain_line(persona: str, subject: str, relation: str) -> str:
    name = _persona(persona)
    target = f"for {subject} {relation}" if subject and relation else "for that"
    tail = 'Say "remember that…" to teach me.'
    if name == "guide":
        lead = f"We can teach a fact. I do not have a verified fact {target}."
    elif name == "builder":
        lead = f"Not a row. I do not have a verified fact {target}."
    elif name == "mythic":
        lead = f"The record does not hold a fact {target}."
    else:
        lead = f"I do not have a verified fact {target}."
    return f"{lead} {tail}"


def _conflict_line(persona: str, subject: str, relation: str, shown: str) -> str:
    name = _persona(persona)
    body = (
        f"The store holds more than one {relation} for {subject}: {shown}. "
        "I will not pick one."
    )
    if name == "guide":
        return f"I cannot choose here. {body}"
    if name == "builder":
        return f"Conflict. {body}"
    if name == "mythic":
        return f"The record disagrees. {body}"
    return body


def _preference_line(persona: str, topic: str, *, dislike: bool) -> str:
    del persona
    verb = "do not like" if dislike else "like"
    return (
        f"I will keep that you {verb} {topic}. "
        "That stays a preference, not a stored fact."
    )


def _lesson_hit(lessons: list[str], subject: str, relation: str, value: str) -> bool:
    needle = f"learned {subject} {relation} {value} under verification"
    return any(str(item).strip() == needle for item in lessons)


def _care_clause(hub_id: str, values: list[str]) -> str:
    if not hub_id or not values:
        return ""
    try:
        from resileos.kin.aphrodite import get_store

        state = get_store().get(hub_id)
    except (ValueError, OSError):
        return ""
    for value in values:
        key = value.strip().lower()[:80]
        entry = state.preferences.get(key)
        if entry and float(entry.get("weight") or 0.0) > 0.0:
            return f" I am keeping care on {value}."
    return ""


def _hades_store() -> Any:
    from resileos.kin.hades import make_hades
    from resileos.kin.wiring import get_kin_bundle

    bundle = get_kin_bundle()
    store = getattr(bundle, "_hades", None)
    if store is None:
        store = make_hades()
        bundle._hades = store
    return store


def remember_verified_learn(hub_id: str, subject: str, relation: str, obj: str) -> str | None:
    """Record a lesson and an Aphrodite care weight. Does not call learn."""
    from resileos.chat.ledger import normalize_hub_id
    from resileos.harness.packet import ControlPacket
    from resileos.kin.aphrodite import get_store

    try:
        hub = normalize_hub_id(hub_id)
    except ValueError:
        return None
    lesson = f"learned {subject} {relation} {obj} under verification"
    packet = ControlPacket(id=f"chat-learn-{hub}")
    packet.verified = True
    _hades_store().save(
        packet,
        lesson=lesson,
        extra={"hub_id": hub, "kind": "learn", "lesson_only": True},
    )
    topic = str(obj).strip().lower()[:80]
    if topic:
        try:
            state = get_store().get(hub)
            state.update_preference(topic, like=True, care=1)
            get_store().save(hub)
        except (ValueError, OSError):
            pass
    return lesson


def budgeted_lessons(hub_id: str, *, max_items: int = LESSON_BUDGET) -> list[str]:
    """Recent verified learn-lessons for this hub, trimmed by Hermes.

    The navigator sees the lesson string only. Checkpoint history, evidence,
    and scars stay in Hades.
    """
    from resileos.chat.ledger import normalize_hub_id

    try:
        hub = normalize_hub_id(hub_id)
    except ValueError:
        return []
    store = _hades_store()
    files = list(store.store_dir.glob("*.json"))
    files.sort(key=lambda path: (path.stat().st_mtime, path.name))
    found: list[str] = []
    for path in reversed(files):
        checkpoint = store.load(path.stem)
        if checkpoint is None or not checkpoint.verified:
            continue
        extra = checkpoint.extra or {}
        if extra.get("kind") != "learn" or extra.get("hub_id") != hub:
            continue
        lesson = str(checkpoint.lesson or "").strip()
        if not lesson.startswith("learned ") or " under verification" not in lesson:
            continue
        found.append(lesson)
        if len(found) >= max(0, int(max_items)):
            break
    found.reverse()
    items = [
        {"subject": "lesson", "relation": "learned", "obj": text, "lesson": text}
        for text in found
    ]
    navigate, _handler = make_hermes_navigator(max_depth=2, max_items=max_items)
    budget = HermesBudget(max_depth=2, max_items=max_items)
    ranked = list(navigate(items, budget))
    return [str(item.get("lesson") or "") for item in ranked if item.get("lesson")]


def _ground(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Deterministic custom mouth plus the language codex. No model function."""
    if not rows:
        return {
            "text": "",
            "backend": "structured",
            "epistemic": epistemic_label([]),
            "codex": "",
            "grammar": None,
        }
    try:
        grounded = custom_answer(rows, "")
    except Exception:
        grounded = {
            "text": "",
            "backend": "structured",
            "epistemic": epistemic_label(rows),
        }
    try:
        spoken = speak(rows)
        codex_text = str(spoken.get("text") or "")
    except Exception:
        codex_text = ""
    try:
        grammar = grammar_of(rows)
    except Exception:
        grammar = None
    return {
        "text": str(grounded.get("text") or ""),
        "backend": str(grounded.get("backend") or "structured"),
        "epistemic": str(grounded.get("epistemic") or epistemic_label(rows)),
        "codex": codex_text,
        "grammar": grammar,
    }


def _structured(
    status: str,
    subject: str,
    relation: str | None,
    rows: list[str],
    obj: str | None,
    prior: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "subject": subject,
        "relation": relation,
        "rows": list(rows),
        "obj": obj,
        "value": prior,
    }


def render_persona_mouth(
    *,
    status: str,
    persona: str,
    subject: str = "",
    relation: str | None = None,
    rows: list[Any] | None = None,
    obj: str | None = None,
    wrote: bool = False,
    router_class: str = "",
    action_name: str = "",
    verified: bool = False,
    allow_mouth: bool = False,
    prose: bool = True,
    lessons: list[str] | None = None,
    hub_id: str = "",
    frame_tag: str | None = None,
    finished_frames: frozenset[str] | set[str] | None = None,
    prior_reply: str = "",
    groups: list[tuple[str, list[str]]] | None = None,
) -> dict[str, Any]:
    """Expand one structured turn. ``apply`` is false when prose stays off."""
    shown_rows = [str(row) for row in (rows or []) if str(row).strip()]
    rel = str(relation or "")
    lesson_window = [str(item) for item in (lessons or []) if str(item).strip()]
    envelope = build_envelope(
        persona,
        hub_scope=f"user:{hub_id}" if hub_id else "user:",
        hermes_depth=2 if verified else 0,
        frame_tag=frame_tag,
        finished_frames=finished_frames,
    )
    # should_render_prose(False) stays closed. A true request does not
    # skip the gate: facts still need this cycle's verified flag. Metis
    # allow_mouth may open a non-factual line. The turn already cycled,
    # so this call does not start another one.
    gate_open = should_render_prose(
        bool(prose),
        require_verified=True,
        run_cycle=False,
        default_if_no_policy=True,
    )
    prose_requested = bool(prose)
    factual_ok = bool(prose and verified and (gate_open or verified))
    soft_ok = bool(prose and (verified or allow_mouth or gate_open))
    structured = _structured(status, subject, relation, shown_rows, obj, prior_reply)
    frame = classify_decision(
        "accept" if status == "ACCEPTED" and factual_ok else "abstain",
        subject=subject,
        has_source=bool(factual_ok and shown_rows),
        conflict=status == "CONFLICT",
    )
    audit: dict[str, Any] = {
        "rendered": False,
        "backend": "structured",
        "epistemic": "ABSTAINED",
        "factual": False,
        "codex": "",
        "grammar": None,
        "envelope": {
            "persona": envelope["persona"],
            "frame_tag": envelope["frame_tag"],
            "branched": envelope["branched"],
            "honesty": envelope["weights"]["honesty"],
            "fluency": envelope["weights"]["fluency"],
            "charm": envelope["weights"]["charm"],
            "writes_residual": False,
        },
        "lessons": list(lesson_window),
        "frame": frame,
        "prose_requested": bool(prose_requested),
    }
    result = {
        "apply": False,
        "text": "",
        "factual": False,
        "structured": structured,
        "audit": audit,
        "lessons": list(lesson_window),
    }
    if not prose_requested:
        return result

    if groups:
        pairs = [(str(pair_rel), [str(v) for v in vals if str(v).strip()]) for pair_rel, vals in groups]
        pairs = [(pair_rel, vals) for pair_rel, vals in pairs if pair_rel and vals]
    elif rel and shown_rows:
        pairs = [(rel, shown_rows)]
    else:
        pairs = []

    def _finish(text: str, *, factual: bool, grounded: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = [subject, rel, str(obj or ""), *shown_rows, *lesson_window]
        for pair_rel, vals in pairs:
            allowed.append(pair_rel)
            allowed.extend(vals)
        from resileos.chat.turn_cycle import ORIENTATION

        fixed = set(_SOFT.values()) | set(ORIENTATION.values())
        stray = [] if text in fixed else unsupported_tokens(text, allowed)
        spoken = text
        if stray:
            audit["stray"] = stray
            spoken = ""
            factual = False
        if grounded:
            audit["backend"] = grounded["backend"]
            audit["epistemic"] = grounded["epistemic"]
            audit["codex"] = grounded["codex"]
            audit["grammar"] = grounded["grammar"]
        else:
            audit["epistemic"] = "ABSTAINED" if not factual else "GROUNDED"
        if spoken:
            try:
                audit["language"] = detect_language(spoken).get("guess")
            except Exception:
                audit["language"] = None
        audit["rendered"] = bool(spoken)
        audit["factual"] = bool(factual and spoken)
        result["apply"] = bool(spoken)
        result["text"] = spoken
        result["factual"] = bool(factual and spoken)
        return result

    if not verified and shown_rows and status in {"ACCEPTED", "CONFLICT"}:
        from resileos.chat.turn_cycle import orientation_text

        return _finish(orientation_text(_persona(persona)), factual=False)

    if not verified and router_class == "SOFT_CHAT" and not soft_ok:
        return result

    if action_name == "preference" and (verified or soft_ok):
        topic = str(obj or "").strip()
        dislike = prior_reply.lower().startswith("recorded dislike")
        if not topic:
            return result
        return _finish(_preference_line(persona, topic, dislike=dislike), factual=False)

    if router_class == "SOFT_CHAT" and status in {"ACCEPTED", "MOUTH_CLOSED"} and not shown_rows:
        if verified or soft_ok:
            return _finish(_soft_line(persona), factual=False)
        return result

    if status == "CONFLICT" and pairs and factual_ok:
        pair_rel, vals = pairs[0]
        grounded = _ground(
            [{"subject": subject, "relation": pair_rel, "obj": value} for value in vals]
        )
        return _finish(
            _conflict_line(persona, subject, pair_rel, _join(vals)),
            factual=False,
            grounded=grounded,
        )

    if status in {"ABSTAINED", "NO_ROWS", "MOUTH_CLOSED"} and not (status == "MOUTH_CLOSED" and verified):
        if status == "MOUTH_CLOSED" and not verified:
            return result
        return _finish(_abstain_line(persona, subject, rel), factual=False)

    if not factual_ok or not pairs:
        if router_class == "SOFT_CHAT" and soft_ok:
            return _finish(_soft_line(persona), factual=False)
        return result

    row_dicts = [
        {"subject": subject, "relation": pair_rel, "obj": value}
        for pair_rel, vals in pairs
        for value in vals
    ]
    grounded = _ground(row_dicts)
    sentences: list[str] = []
    mentioned = False
    care_values: list[str] = []
    for pair_rel, vals in pairs:
        shown = _join(vals)
        if wrote:
            sentences.append(_learn_line(persona, subject, pair_rel, shown))
        else:
            sentences.append(_fact_line(persona, subject, pair_rel, shown))
        care_values.extend(vals)
        if not wrote and any(_lesson_hit(lesson_window, subject, pair_rel, value) for value in vals):
            mentioned = True
    text = " ".join(sentences)
    if mentioned:
        text += " I stored that under verification."
    text += _care_clause(hub_id, care_values)
    return _finish(text, factual=True, grounded=grounded)
