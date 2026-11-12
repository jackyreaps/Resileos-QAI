"""Bounded Kin cycle for one ordinary chat turn.

History is kept under a Hermes item budget. A residual address of the
turn is the evidence a cycle can verify. Assertive mouth and residual
writes wait on that verification (or, for mouth only, the Metis
allow_mouth policy). Aphrodite may attach a tutorial fragment after a
verified cycle. It does not learn triples.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from resileos.chat.ledger import HUB_RELATIONS, user_subject
from resileos.chat.router import parse_teach, parse_world_teach, teach_cue
from resileos.kin.hermes import HermesBudget, make_hermes_navigator

HERMES_MAX_ITEMS = 8
HERMES_MAX_DEPTH = 2

COMPANION_INTRO = (
    "Sign in with a username to keep this thread. "
    'Teach a fact with "remember …", then ask it back. '
    "Stores · Derives · Abstains: exact rows are stored, an answer is derived only from those rows, "
    "and an unknown is abstained instead of invented. "
    "Studio, Kin, and the ledger are in the header."
)

UNVERIFIED_WRITE = (
    "This cycle did not verify, so nothing was stored. "
    'Teach it again on a verified turn, attach a document, or ask a clearer line.'
)

ORIENTATION = {
    "honest": (
        "Checking the record… I will not invent a fact for this. "
        'Teach one with "remember that…", attach a document, or ask a stored subject and relation.'
    ),
    "guide": (
        "Checking the record… We can teach a fact, recall one, or abstain. "
        "I will not fill a gap with a guess."
    ),
    "builder": "Checking the record… Teach a row, ask one, or run a tool. This turn adds no fact.",
    "mythic": "Checking the record… I hear you. Nothing unstored will be stated as a fact.",
}

_FOLLOW = re.compile(r"(?i)^(?:and|also|what about|how about)\s+(.+?)\s*\??$")
_WHAT_RELATION = re.compile(r"(?i)\bwhat is the (\w+) of\b")
_PRONOUNS = {
    "then",
    "that",
    "it",
    "this",
    "them",
    "those",
    "him",
    "her",
    "there",
}
_ABSTAIN_MARKS = (
    "no rows were returned",
    "no channel",
    "don't have a verified fact",
    "do not have a verified fact",
    "nothing was stored",
    "this cycle did not verify",
)


class LearnProxy:
    """Hide learn. Zeus already applied the approved triple."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def learn(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def orientation_text(persona: str) -> str:
    return ORIENTATION.get(persona, ORIENTATION["honest"])


def budget_history(
    history: list[dict] | None,
    *,
    max_items: int = HERMES_MAX_ITEMS,
) -> list[dict[str, Any]]:
    """Keep the recent window, then let Hermes rank inside that budget.

    The returned list is chronological. ``budget_used`` is stored on a
    side list attribute so callers can see the navigator's cap.
    """
    cleaned: list[dict[str, Any]] = []
    for raw in history or []:
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or raw.get("text") or "").strip()
        if not content:
            continue
        item: dict[str, Any] = {
            "role": str(raw.get("role") or "user"),
            "content": content[:500],
        }
        subject = str(raw.get("subject") or "").strip()
        relation = str(raw.get("relation") or "").strip()
        obj = raw.get("obj", raw.get("value"))
        if subject and relation:
            item["subject"] = subject
            item["relation"] = relation
        if obj is not None and str(obj).strip():
            item["obj"] = str(obj).strip()[:200]
        cleaned.append(item)
    window = cleaned[-max(0, int(max_items)) :]
    navigate, _handler = make_hermes_navigator(
        max_depth=HERMES_MAX_DEPTH, max_items=max_items
    )
    budget = HermesBudget(max_depth=HERMES_MAX_DEPTH, max_items=max_items)
    ranked = list(navigate(window, budget))
    window_ids = {id(item): index for index, item in enumerate(window)}
    ranked.sort(key=lambda item: window_ids.get(id(item), 0))
    # Hermes may drop items. The kept set stays in chronological order.
    return ranked if window else []


def _relation_names(titanos: Any) -> dict[str, str]:
    names: dict[str, str] = {}
    for key in getattr(titanos, "relations", {}) or {}:
        names.setdefault(str(key).lower(), str(key))
    return names


def last_relation(window: list[dict[str, Any]], titanos: Any) -> str:
    """Latest relation in the budgeted window. Structured rows win ties by recency."""
    names = _relation_names(titanos)
    structured = [item for item in window if item.get("relation")]
    if structured:
        token = str(structured[-1]["relation"])
        return names.get(token.lower(), token)
    for item in reversed(window):
        text = str(item.get("content") or "")
        named = _WHAT_RELATION.search(text)
        if named and named.group(1).lower() in names:
            return names[named.group(1).lower()]
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text):
            if token.lower() in names:
                return names[token.lower()]
    return ""


def continuation_text(text: str, window: list[dict[str, Any]], titanos: Any) -> str:
    """Reuse the prior relation for a short follow-up. Does not invent a relation."""
    raw = (text or "").strip()
    if not raw or teach_cue(raw) or raw.startswith("/"):
        return raw
    match = _FOLLOW.match(raw)
    if not match:
        return raw
    tail = match.group(1).strip().strip("?.!\"'")
    if not tail or tail.lower() in _PRONOUNS or teach_cue(tail) or len(tail.split()) > 6:
        return raw
    relation = last_relation(window, titanos)
    if not relation:
        return raw
    return f"what is the {relation} of {tail}"


def infer_last_tool_empty(window: list[dict[str, Any]], client_flag: bool) -> bool:
    if client_flag:
        return True
    for item in reversed(window):
        if str(item.get("role") or "") != "assistant":
            continue
        content = str(item.get("content") or "").lower()
        return any(mark in content for mark in _ABSTAIN_MARKS)
    return False


def metrics_from_history(window: list[dict[str, Any]]) -> dict[str, Any]:
    hits = misses = teaches = sessions = 0
    for item in window:
        content = str(item.get("content") or "")
        if str(item.get("role") or "") == "user":
            sessions += 1
            if teach_cue(content):
                teaches += 1
            continue
        low = content.lower()
        if any(mark in low for mark in _ABSTAIN_MARKS):
            misses += 1
        elif item.get("subject") and item.get("relation") and item.get("obj"):
            hits += 1
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "teaches": teaches,
        "sessions": sessions,
        "hit_rate": (hits / total) if total else 0.0,
    }


def turn_residual(text: str) -> dict[str, Any]:
    """Residual address of this turn. The hash is evidence, not a fact."""
    from resileos.ui.core_bridge import core_step_from_address
    from resileos.ui.perceive_language import perceive_language

    perceived = perceive_language(text or " ", subject="chat")
    embed = dict(perceived.get("address") or {})
    core = core_step_from_address(embed)
    raw = "|".join(
        [
            str(embed.get("belt")),
            str(embed.get("frame")),
            str(embed.get("residual_bin")),
            str(embed.get("mean_luma")),
            str(embed.get("edge_density")),
            str(core.get("backend")),
            str(core.get("packet_hash")),
            text or "",
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return {
        "packet_hash": digest,
        "topics": [],
        "address": embed,
        "backend": core.get("backend"),
    }


def writable_triple(
    text: str,
    hub_id: str,
    force_class: str | None,
) -> tuple[str, str, str] | None:
    """Triple dispatch would learn. None when this turn is not a write."""
    forced = (force_class or "").strip() or None
    if forced and forced != "HUB_LEARN":
        return None
    if forced != "HUB_LEARN" and not teach_cue(text):
        return None
    world = parse_world_teach(text)
    if world:
        return world
    relation, obj = parse_teach(text)
    if relation not in HUB_RELATIONS or not obj:
        return None
    return user_subject(hub_id), relation, obj


def zeus_learn(titanos: Any, triple: tuple[str, str, str]) -> dict[str, Any]:
    """Reviewers approve, then Zeus learns. A rejection writes nothing."""
    from resileos.harness.packet import ControlPacket
    from resileos.harness.separated import Proposal, SeparatedCycle, zeus_head

    subject, relation, obj = triple
    cycle = SeparatedCycle(id_prefix="chat")
    packet = ControlPacket(id=f"chat-learn-{subject}-{relation}")
    proposal = Proposal(
        id=packet.id,
        writer="chat",
        action_type="learn",
        result={"status": "ok", "rows": [{"subject": subject, "relation": relation, "obj": obj}]},
        claims=[(subject, relation, obj)],
        packet=packet,
    )

    def ask(sub: str, rel: str) -> Any:
        rows = titanos.ask_list(sub, rel)
        if not rows:
            return None
        return rows if len(rows) > 1 else rows[0]

    return zeus_head(
        proposal,
        [
            ("verifiers", lambda item: cycle.review_verifiers(item)),
            ("council", lambda item: cycle.review_council(item, ask_fn=ask, profile="personal")),
        ],
        titanos.learn,
    )


def run_bounded_cycle(
    text: str,
    window: list[dict[str, Any]],
    hub_id: str,
    titanos: Any,
) -> dict[str, Any]:
    """One Iris → Metis cycle with harness guards, Aphrodite, and Hades."""
    from resileos.harness.packet import ControlPacket
    from resileos.kin.aphrodite import get_store
    from resileos.kin.legions import LegionError, invoke_legion
    from resileos.kin.wiring import get_kin_bundle

    bundle = get_kin_bundle()
    # A fresh packet so an earlier turn's evidence cannot verify this one.
    bundle.control = ControlPacket(id="chat-turn")
    packet = turn_residual(text)
    metrics = metrics_from_history(window)
    state = None
    stage_before = 0
    store = None
    try:
        store = get_store()
        state = store.get(hub_id)
        stage_before = int(state.tutorial_stage)
    except ValueError:
        state = None
        store = None
    if bundle.control is not None:
        bundle.control.append(
            {
                "event": "chat_history",
                "used": len(window),
                "max_items": HERMES_MAX_ITEMS,
            }
        )
    _report, policy, harness = bundle.cycle(
        metrics=metrics,
        agency_group=getattr(titanos, "agency", None),
        apply_policy=True,
        residual_packet=packet,
        aphrodite_state=state,
    )
    if store is not None and state is not None and harness.get("verified"):
        try:
            store.save(hub_id)
        except ValueError:
            pass
    legions = _companion_legions(
        invoke_legion,
        LegionError,
        hub_id,
        str(packet.get("packet_hash") or ""),
    )
    return {
        "verified": bool(harness.get("verified")),
        "allow_mouth": bool(getattr(policy, "allow_mouth", False)),
        "tutorial_fragment": harness.get("tutorial_fragment"),
        "checkpoint": harness.get("checkpoint"),
        "reason": harness.get("reason") or "",
        "packet_hash": str(packet.get("packet_hash") or ""),
        "stage_before": stage_before,
        "history_used": len(window),
        "legions": legions,
    }


def _companion_legions(invoke, error_type, hub_id: str, packet_hash: str) -> dict[str, Any]:
    """Calliope and Ligeia draft guidance. They do not write residual facts."""
    packet = {"id": "chat-companion", "budget_remaining": {"steps": 3, "cost": 1.0}}
    out: dict[str, Any] = {}
    try:
        draft = invoke(
            "aphrodite",
            "calliope",
            packet,
            hub_id=hub_id,
            residual_hash=packet_hash,
        )
        out["calliope"] = {
            "writes_residual": bool(draft.get("writes_residual")),
            "has_suggestion": bool(draft.get("suggestion")),
        }
    except error_type:
        out["calliope"] = {"writes_residual": False, "has_suggestion": False}
    try:
        cue = invoke("aphrodite", "ligeia", packet, hub_id=hub_id)
        out["ligeia"] = {
            "writes_residual": bool(cue.get("writes_residual")),
            "suggestion_only": bool(cue.get("suggestion_only")),
        }
    except error_type:
        out["ligeia"] = {"writes_residual": False, "suggestion_only": True}
    return out


def message_kind(body: dict[str, Any]) -> str:
    action = body.get("action_taken") or {}
    if action.get("action") == "search" or action.get("tool") == "web_search":
        return "search"
    if body.get("source") == "tool":
        return "tool"
    status = str(body.get("status") or "")
    if status in {"ABSTAINED", "NO_ROWS", "CONFLICT"} or action.get("class") == "ABSTAIN_SURFACE":
        return "abstain"
    if status == "MOUTH_CLOSED":
        return "orientation"
    klass = str(action.get("class") or "")
    if klass in {"TOOL_FACT", "HUB_LEARN", "HUB_RECALL"} and status == "ACCEPTED":
        return "residual"
    if klass == "SOFT_CHAT" and status == "ACCEPTED":
        return "mouth"
    if body.get("companion_prompt"):
        return "companion"
    return "orientation"


def attach_turn_fields(
    body: dict[str, Any],
    *,
    window: list[dict[str, Any]],
    cycle: dict[str, Any] | None,
    assertive: bool,
) -> dict[str, Any]:
    body["history_used"] = len(window)
    body["hermes_budget"] = {"max_items": HERMES_MAX_ITEMS, "used": len(window)}
    verified = bool(cycle and cycle.get("verified"))
    body["cycle_verified"] = verified
    body["mouth_open"] = bool(assertive) if cycle else False
    if cycle is not None:
        body["allow_mouth"] = bool(cycle.get("allow_mouth"))
    if cycle:
        kin = {
            "verified": verified,
            "allow_mouth": bool(cycle.get("allow_mouth")),
            "checkpoint": cycle.get("checkpoint"),
            "reason": cycle.get("reason") or "",
        }
        body["kin"] = kin
        if cycle.get("legions"):
            body["legions"] = cycle["legions"]
        if int(cycle.get("stage_before") or 0) == 0:
            body["companion_prompt"] = COMPANION_INTRO
        fragment = body.get("tutorial_fragment") or cycle.get("tutorial_fragment")
        if fragment and verified and body.get("status") in {"ACCEPTED", "ABSTAINED"}:
            body["tutorial_fragment"] = fragment
    body["message_kind"] = message_kind(body)
    return body
