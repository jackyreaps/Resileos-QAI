"""Psyche kin: mind state for deep worlds, meta frames, and drives.

Holds phase, belt, residual bin, persona, a frame stack, and endocrine drives.
Does not invent facts. Perception writes in. Frames and drives are consumed
from finished Human Medium materials. State persists as hub rows.
"""
from __future__ import annotations

from typing import Any

from resileos.kin.drives import default_drives, drive_rows, update_drives


class Psyche:
    def __init__(self, subject: str = "user:mind") -> None:
        self.subject = subject
        self.state: dict[str, Any] = {
            "phase": 0.0,
            "belt": 0,
            "residual_bin": "low_low",
            "persona": "",
            "mood": "steady",
            "focus": 0.5,
            "depth": 0,
            "frames": [],
            "drives": default_drives(),
        }

    def write_perception(self, perceived: dict[str, Any]) -> dict[str, Any]:
        addr = perceived.get("address") or {}
        self.state["belt"] = int(addr.get("belt", self.state["belt"]))
        self.state["residual_bin"] = str(addr.get("residual_bin", self.state["residual_bin"]))
        val = perceived.get("mean_luma") or perceived.get("energy") or perceived.get("tokens")
        if val is not None:
            self.state["phase"] = float(val)
        return dict(self.state)

    def push_frame(self, frame: dict[str, Any]) -> dict[str, Any]:
        label = str(frame.get("label", "")).strip()
        if not label:
            return dict(self.state)
        row = {
            "label": label,
            "depth": int(frame.get("depth", self.state["depth"] + 1)),
            "parent": frame.get("parent"),
        }
        self.state["frames"].append(row)
        self.state["depth"] = row["depth"]
        return dict(self.state)

    def set_drives(self, signal: dict[str, float]) -> dict[str, Any]:
        self.state["drives"] = update_drives(self.state["drives"], signal)
        return dict(self.state)

    def current_frame(self) -> dict[str, Any] | None:
        frames = self.state["frames"]
        return frames[-1] if frames else None

    def hub_rows(self) -> list[dict[str, str]]:
        s = self.state
        rows = [
            {"subject": self.subject, "relation": "phase", "obj": str(round(float(s["phase"]), 4))},
            {"subject": self.subject, "relation": "belt", "obj": str(s["belt"])},
            {"subject": self.subject, "relation": "residual_bin", "obj": str(s["residual_bin"])},
            {"subject": self.subject, "relation": "persona", "obj": s["persona"] or "none"},
            {"subject": self.subject, "relation": "mood", "obj": s["mood"]},
            {"subject": self.subject, "relation": "depth", "obj": str(s["depth"])},
        ]
        cur = self.current_frame()
        if cur:
            rows.append({"subject": self.subject, "relation": "frame", "obj": cur["label"]})
        rows.extend(drive_rows(self.subject, s["drives"]))
        return rows
