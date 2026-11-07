"""
User profile + persona envelope helpers (hub-scoped).

Stores preferences under user:<id>:* via Titanos learn/query API payloads.
Does not invent biographical facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

ApiCall = Callable[[str, dict], tuple[int, Any]]

PERSONA_PACKS = {
    "honest": {
        "label": "Honest operator",
        "style": "Direct, precise, never invents. Prefers structured facts.",
        "tone": "neutral",
    },
    "guide": {
        "label": "Guide",
        "style": "Clear teaching tone; explains empty results and next steps.",
        "tone": "friendly",
    },
    "builder": {
        "label": "Builder",
        "style": "Terse, action-oriented; favors commands and checklists.",
        "tone": "terse",
    },
    "mythic": {
        "label": "Mythic light",
        "style": "Slightly elevated diction; still refuses unstored claims.",
        "tone": "elevated",
    },
}


@dataclass
class UserProfile:
    user_id: str
    display_name: str = ""
    persona: str = "honest"
    interests: list[str] = field(default_factory=list)
    prefs: dict[str, str] = field(default_factory=dict)
    turn_count: int = 0

    def subject(self) -> str:
        return f"user:{self.user_id}"

    def pack(self) -> dict[str, str]:
        return PERSONA_PACKS.get(self.persona, PERSONA_PACKS["honest"])


def save_profile_facts(profile: UserProfile, post: ApiCall) -> int:
    s = profile.subject()
    facts = [
        [s, "persona", profile.persona],
        [s, "display_name", profile.display_name or profile.user_id],
        [s, "turn_count", str(profile.turn_count)],
    ]
    for interest in profile.interests[:12]:
        facts.append([s, "interest", interest[:80]])
    for k, v in list(profile.prefs.items())[:20]:
        facts.append([s, f"pref_{k}"[:40], str(v)[:120]])
    code, _ = post("/learn_batch", {"facts": facts})
    if code == 200:
        return len(facts)
    n = 0
    for a, b, c in facts:
        code, _ = post("/learn", {"subject": a, "relation": b, "obj": c})
        if code == 200:
            n += 1
    return n


def load_profile(user_id: str, post: ApiCall) -> UserProfile:
    uid = "".join(
        c for c in user_id.strip().lower() if c.isalnum() or c in "_-"
    )[:64] or "anon"
    p = UserProfile(user_id=uid)
    s = p.subject()

    def q(rel: str) -> list[str]:
        code, body = post("/query", {"subject": s, "relation": rel})
        if code != 200 or not isinstance(body, dict):
            return []
        rows = body.get("rows")
        if rows:
            return [str(r) for r in rows]
        val = body.get("value")
        if val is not None:
            return [str(val)]
        return []

    names = q("display_name")
    if names:
        p.display_name = names[-1]
    personas = q("persona")
    if personas and personas[-1] in PERSONA_PACKS:
        p.persona = personas[-1]
    p.interests = list(dict.fromkeys(q("interest")))[:12]
    turns = q("turn_count")
    if turns:
        try:
            p.turn_count = int(str(turns[-1]))
        except ValueError:
            pass
    return p


def shape_reply(text: str, profile: UserProfile) -> str:
    """Client-side tone only — never adds factual claims."""
    pack = profile.pack()
    tone = pack.get("tone", "neutral")
    name = profile.display_name or profile.user_id
    prefix = ""
    if profile.turn_count <= 2 and name and name not in ("anon", ""):
        prefix = f"*{name}* — "
    if tone == "terse":
        t = text.replace(
            "📭 **Not in the store** — intentional.", "Not in store."
        )
        t = t.replace(
            "Teach with: `remember Subject relation object`",
            "Teach: remember S R O",
        )
        return prefix + t
    if tone == "friendly" and (
        "Not in store" in text or "not in store" in text.lower()
    ):
        return (
            prefix
            + text
            + "\n\nWhen you're ready: `remember Subject relation object`."
        )
    return prefix + text


def extract_interest_signal(user_text: str) -> str | None:
    t = user_text.lower()
    for needle, tag in (
        ("image", "media"),
        ("draw", "media"),
        ("video", "media"),
        ("sparql", "search"),
        ("search", "search"),
        ("guild", "guild"),
        ("myth", "mythology"),
        ("code", "engineering"),
        ("build", "engineering"),
    ):
        if needle in t:
            return tag
    return None

def persona_phase(persona: str) -> float:
    """Stable phase offset for the scale address. Empty persona is 0."""
    if not persona:
        return 0.0
    return (sum(ord(c) for c in persona) % 360) * 3.141592653589793 / 180.0
