"""Versioned self-facts seed. This is the latent tier's starting frame."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from resileos.persona.principal import PersonaError

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT = _REPO / "configs" / "persona" / "self_facts.json"

LABEL_SEED = "verified-seed"


@dataclass(frozen=True)
class SelfFacts:
    version: int
    updated: str
    facts: tuple[dict, ...]
    tutorial: tuple[dict, ...]
    path: str

    def latent_frame(self) -> dict[str, dict]:
        """Seed cells. Personal data is not part of this frame."""
        frame: dict[str, dict] = {}
        for row in (*self.facts, *self.tutorial):
            cell = _seed_cell(row)
            frame[cell["id"]] = cell
        return frame

    def public_rows(self) -> list[dict]:
        rows = []
        for row in self.facts:
            rows.append(
                {
                    "id": row["id"],
                    "topic": row["topic"],
                    "text": row["text"],
                    "label": LABEL_SEED,
                    "source": f"seed:{row['check']}",
                }
            )
        return rows

    def tutorial_rows(self) -> list[dict]:
        rows = []
        for row in self.tutorial:
            rows.append(
                {
                    "id": row["id"],
                    "label_text": row["label"],
                    "text": row["text"],
                    "label": LABEL_SEED,
                    "source": f"seed:{row['check']}",
                }
            )
        return rows

    def step_for_fragment(self, fragment: str) -> dict | None:
        needle = (fragment or "").strip()
        for row in self.tutorial:
            if row["text"] == needle:
                return row
        return None


def _seed_cell(row: dict) -> dict:
    topic = str(row.get("topic") or "tutorial")
    return {
        "id": row["id"],
        "text": row["text"],
        "kind": topic,
        "label": LABEL_SEED,
        "source": f"seed:{row['check']}",
        "personal": False,
        "stated_at": "",
        "updated_at": "",
    }


def load_self_facts(path: str | Path | None = None) -> SelfFacts:
    chosen = Path(path or os.environ.get("RESILEOS_PERSONA_SEED") or _DEFAULT)
    try:
        raw = json.loads(chosen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PersonaError(f"self-facts seed is unreadable: {chosen}") from exc
    version = raw.get("version")
    if not isinstance(version, int) or version < 1:
        raise PersonaError("self-facts version must be an integer >= 1")
    facts = tuple(_check_row(row, topic=True) for row in raw.get("facts") or [])
    tutorial = tuple(_check_row(row, topic=False) for row in raw.get("tutorial") or [])
    if not facts or not tutorial:
        raise PersonaError("self-facts seed needs facts and tutorial steps")
    return SelfFacts(
        version=version,
        updated=str(raw.get("updated") or ""),
        facts=facts,
        tutorial=tutorial,
        path=str(chosen),
    )


def _check_row(row: dict, *, topic: bool) -> dict:
    if not isinstance(row, dict):
        raise PersonaError("seed row must be an object")
    for key in ("id", "text", "check", "needle"):
        if not str(row.get(key) or "").strip():
            raise PersonaError(f"seed row missing {key}")
    if topic and not str(row.get("topic") or "").strip():
        raise PersonaError("seed fact missing topic")
    if not topic and not str(row.get("label") or "").strip():
        raise PersonaError("tutorial step missing label")
    return dict(row)
