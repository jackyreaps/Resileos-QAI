"""Aphrodite — preferences, care weights, persona, and tutorial steps.

Does not write residual facts. Optional human_signals default to 0.5
when a key is missing. Legions: Calliope, Ligeia, Echo.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from resileos.chat.ledger import normalize_hub_id

STEPS: tuple[str, ...] = (
    "teach_fact",
    "recall_fact",
    "abstain_unknown",
    "edit_ledger",
    "run_tool",
    "kin_cycle",
    "try_legion",
    "set_preference",
)

STEP_LABELS: dict[str, str] = {
    "teach_fact": "Teach a fact",
    "recall_fact": "Recall it",
    "abstain_unknown": "See ABSTAIN on an unknown",
    "edit_ledger": "Edit a ledger row",
    "run_tool": "Run a tool",
    "kin_cycle": "Run a Kin cycle",
    "try_legion": "Try a legion",
    "set_preference": "Set a like or a dislike",
}

FRAGMENTS: dict[str, str] = {
    "teach_fact": "A taught line is stored as a triple.",
    "recall_fact": "Recall returns stored rows only.",
    "abstain_unknown": "An unknown question returns ABSTAIN.",
    "edit_ledger": "A ledger edit changes one hub row.",
    "run_tool": "A tool returns its own result.",
    "kin_cycle": "A verified Kin cycle keeps the lesson.",
    "try_legion": "A legion runs under one Kin.",
    "set_preference": "Likes and dislikes stay here. They are not residual facts.",
}

_PERSONAE: tuple[dict[str, str], ...] = (
    {"name": "Companion", "tone": "neutral", "sigil": "circle", "chapter": ""},
    {"name": "Scribe", "tone": "plain", "sigil": "line", "chapter": "facts"},
    {"name": "Reader", "tone": "plain", "sigil": "line", "chapter": "recall"},
    {"name": "Gate", "tone": "exact", "sigil": "bar", "chapter": "abstain"},
    {"name": "Keeper", "tone": "exact", "sigil": "bar", "chapter": "ledger"},
    {"name": "Hand", "tone": "direct", "sigil": "mark", "chapter": "tools"},
    {"name": "Walker", "tone": "direct", "sigil": "mark", "chapter": "cycle"},
    {"name": "Courier", "tone": "direct", "sigil": "arc", "chapter": "legion"},
    {"name": "Host", "tone": "warm", "sigil": "arc", "chapter": "preference"},
)


def _blank_preference() -> dict[str, Any]:
    return {"weight": 0.0, "care": 1, "last_seen": 0.0, "likes": 0, "dislikes": 0}


def _blank_persona() -> dict[str, Any]:
    first = _PERSONAE[0]
    return {
        "name": first["name"],
        "tone": first["tone"],
        "sigil": first["sigil"],
        "depth": 1,
        "formality": 0.5,
        "growth_stage": 0,
        "unlocked_chapters": [],
    }


@dataclass
class AphroditeState:
    preferences: dict[str, dict] = field(default_factory=dict)
    persona: dict[str, Any] = field(default_factory=_blank_persona)
    rapport: float = 0.5
    tutorial_stage: int = 0
    completed: list[str] = field(default_factory=list)
    last_growth: float = 0.0
    last_fragment: str = ""

    def update_preference(self, topic: str, *, like: bool = True, care: int = 1) -> None:
        key = (topic or "").strip().lower()[:80]
        if not key:
            raise ValueError("topic is required")
        entry = self.preferences.setdefault(key, _blank_preference())
        entry["last_seen"] = time.time()
        if like:
            entry["likes"] = int(entry.get("likes") or 0) + 1
            entry["weight"] = min(1.0, float(entry.get("weight") or 0.0) + 0.1)
        else:
            entry["dislikes"] = int(entry.get("dislikes") or 0) + 1
            entry["weight"] = max(0.0, float(entry.get("weight") or 0.0) - 0.1)
        entry["care"] = max(int(entry.get("care") or 1), int(care))

    def care_multiplier(self, topic: str) -> float:
        entry = self.preferences.get((topic or "").strip().lower())
        if not entry:
            return 1.0
        return 1.0 + (int(entry.get("care") or 1) * float(entry.get("weight") or 0.0) * 0.5)

    def fold_signals(self, human_signals: Optional[dict] = None) -> None:
        """Missing keys stay at 0.5. No signal dict leaves rapport unchanged."""
        if not human_signals:
            return
        oxtr = float(human_signals.get("oxtr", 0.5))
        coherence = float(human_signals.get("coherence", 0.5))
        self.rapport = 0.6 * float(self.rapport) + 0.4 * ((oxtr + coherence) / 2.0)

    def unfinished(self) -> list[str]:
        done = set(self.completed)
        return [step for step in STEPS if step not in done]

    def peek_fragment(self) -> Optional[str]:
        """Next fragment. Does not advance growth."""
        pending = self.unfinished()
        if not pending:
            return None
        return FRAGMENTS[pending[0]]

    def _apply_persona(self) -> None:
        stage = max(0, min(int(self.tutorial_stage), len(_PERSONAE) - 1))
        chosen = _PERSONAE[stage]
        chapters = list(self.persona.get("unlocked_chapters") or [])
        chapter = chosen.get("chapter") or ""
        if chapter and chapter not in chapters:
            chapters.append(chapter)
        self.persona = {
            "name": chosen["name"],
            "tone": chosen["tone"],
            "sigil": chosen["sigil"],
            "depth": 1 + stage,
            "formality": 0.5,
            "growth_stage": stage,
            "unlocked_chapters": chapters,
        }

    def advance(self, step: str, *, verified: bool) -> Optional[str]:
        """Advance one tutorial step. Unverified calls do not grow."""
        if not verified or step not in FRAGMENTS or step in self.completed:
            return None
        self.completed.append(step)
        self.tutorial_stage = len(self.completed)
        self._apply_persona()
        self.last_growth = time.time()
        self.last_fragment = FRAGMENTS[step]
        return self.last_fragment

    def handle(
        self,
        query: Any = None,
        *,
        residual_hash: str = "",
        human_signals: Optional[dict] = None,
        verified: bool = False,
    ) -> dict[str, Any]:
        """Decline fact routing. A fragment is attached only when verified."""
        del query, residual_hash
        self.fold_signals(human_signals)
        fragment = self.last_fragment if verified and self.last_fragment else None
        return {
            "declined": True,
            "reason": "aphrodite-does-not-route-facts",
            "tutorial_fragment": fragment,
            "care_multipliers": {topic: self.care_multiplier(topic) for topic in self.preferences},
            "writes_residual": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferences": self.preferences,
            "persona": self.persona,
            "rapport": self.rapport,
            "tutorial_stage": self.tutorial_stage,
            "completed": list(self.completed),
            "steps": [
                {"id": step, "label": STEP_LABELS[step], "done": step in self.completed}
                for step in STEPS
            ],
            "care_multipliers": {topic: self.care_multiplier(topic) for topic in self.preferences},
            "last_fragment": self.last_fragment,
            "writes_residual": False,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AphroditeState":
        state = cls(
            preferences=dict(data.get("preferences") or {}),
            persona=dict(data.get("persona") or _blank_persona()),
            rapport=float(data.get("rapport", 0.5)),
            tutorial_stage=int(data.get("tutorial_stage") or 0),
            completed=list(data.get("completed") or []),
            last_growth=float(data.get("last_growth") or 0.0),
            last_fragment=str(data.get("last_fragment") or ""),
        )
        if "growth_stage" not in state.persona:
            state._apply_persona()
        return state


class AphroditeStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, AphroditeState] = {}

    def get(self, hub_id: str) -> AphroditeState:
        hub = normalize_hub_id(hub_id)
        cached = self._mem.get(hub)
        if cached is not None:
            return cached
        path = self.root / f"{hub}.json"
        if path.exists():
            try:
                state = AphroditeState.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                state = AphroditeState()
        else:
            state = AphroditeState()
        self._mem[hub] = state
        return state

    def save(self, hub_id: str) -> AphroditeState:
        hub = normalize_hub_id(hub_id)
        state = self.get(hub)
        payload = state.to_dict()
        payload["last_growth"] = state.last_growth
        (self.root / f"{hub}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return state

    def reset(self, hub_id: str) -> AphroditeState:
        hub = normalize_hub_id(hub_id)
        self._mem.pop(hub, None)
        path = self.root / f"{hub}.json"
        if path.exists():
            path.unlink()
        return self.get(hub)


_STORE: AphroditeStore | None = None


def get_store() -> AphroditeStore:
    global _STORE
    if _STORE is None:
        root = os.environ.get("RESILEOS_APHRODITE_DIR", "data/aphrodite")
        _STORE = AphroditeStore(root)
    return _STORE


def set_store(store: AphroditeStore | None) -> None:
    global _STORE
    _STORE = store


def record_preference(
    hub_id: str,
    topic: str,
    *,
    like: bool = True,
    care: int = 1,
) -> tuple[AphroditeState, str | None]:
    store = get_store()
    state = store.get(hub_id)
    state.update_preference(topic, like=like, care=care)
    fragment = state.advance("set_preference", verified=True)
    store.save(hub_id)
    return state, fragment


def note_router_step(hub_id: str, status: str, action: dict[str, Any]) -> str | None:
    """Map a verified chat outcome onto one tutorial step. No residual write."""
    klass = str(action.get("class") or "")
    step = None
    if klass == "HUB_LEARN" and action.get("wrote") and status == "ACCEPTED":
        step = "teach_fact"
    elif klass == "HUB_RECALL" and status == "ACCEPTED":
        step = "recall_fact"
    elif status == "ABSTAINED":
        step = "abstain_unknown"
    if step is None:
        return None
    try:
        state = get_store().get(hub_id)
    except ValueError:
        return None
    fragment = state.advance(step, verified=True)
    get_store().save(hub_id)
    return fragment


def make_aphrodite_handler(state: Optional[AphroditeState] = None) -> Callable:
    held = state or AphroditeState()

    def handler(query: Any = None, *, residual_hash: str = "", human_signals: Optional[dict] = None, verified: bool = False) -> dict:
        return held.handle(
            query,
            residual_hash=residual_hash,
            human_signals=human_signals,
            verified=verified,
        )

    return handler


def register_aphrodite_legions() -> list[str]:
    """Calliope, Ligeia, and Echo on the Aphrodite Kin. Idempotent."""
    from resileos.kin.legions import register_legion

    def calliope(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Draft the next tutorial fragment from the preference map and residual hash."""
        del seen
        hub = str(kwargs.get("hub_id") or "anon")
        try:
            state = get_store().get(hub)
        except ValueError:
            state = AphroditeState()
        residual_hash = str(kwargs.get("residual_hash") or "")
        return {
            "suggestion": state.peek_fragment(),
            "topic": str(kwargs.get("topic") or ""),
            "evidence": residual_hash,
            "preferences": {
                key: {"weight": row.get("weight"), "care": row.get("care")}
                for key, row in state.preferences.items()
            },
            "writes_residual": False,
        }

    def ligeia(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Soft attention cue toward a high-care or unfinished thread. Suggestion only."""
        del seen
        hub = str(kwargs.get("hub_id") or "anon")
        topic = str(kwargs.get("topic") or "")
        try:
            state = get_store().get(hub)
        except ValueError:
            state = AphroditeState()
        mult = state.care_multiplier(topic) if topic else 1.0
        pending = state.unfinished()
        cue = None
        if topic and mult > 1.2:
            cue = f"high-care:{topic}"
        elif pending:
            cue = f"unfinished:{pending[0]}"
        return {
            "attention_cue": cue,
            "suggestion_only": True,
            "care_multiplier": mult,
            "writes_residual": False,
        }

    def echo(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Micro-probe of a habit. Lesson only, through Hades, not a residual fact."""
        del seen
        probe = str(kwargs.get("probe") or "")
        lesson = f"habit-check:{probe}" if probe else "habit-check"
        checkpoint_id = None
        if kwargs.get("save_lesson"):
            store = kwargs.get("hades")
            if store is None:
                from resileos.kin.hades import make_hades

                store = make_hades()
            from resileos.harness.packet import ControlPacket

            packet = ControlPacket(id="echo-lesson")
            packet.verified = False
            checkpoint_id = store.save(packet, lesson=lesson).id
        return {
            "probe_result": lesson,
            "lesson": lesson,
            "lesson_only": True,
            "checkpoint": checkpoint_id,
            "writes_residual": False,
        }

    registered = [
        register_legion(
            "aphrodite",
            calliope,
            name="calliope",
            constraints={"action": "draft", "writes_residual": False, "executes": True},
        ),
        register_legion(
            "aphrodite",
            ligeia,
            name="ligeia",
            constraints={"action": "cue", "writes_residual": False, "executes": True},
        ),
        register_legion(
            "aphrodite",
            echo,
            name="echo",
            constraints={"action": "probe", "writes_residual": False, "executes": True},
        ),
    ]
    return registered


__all__ = [
    "AphroditeState",
    "AphroditeStore",
    "FRAGMENTS",
    "STEPS",
    "get_store",
    "make_aphrodite_handler",
    "note_router_step",
    "record_preference",
    "register_aphrodite_legions",
    "set_store",
]
