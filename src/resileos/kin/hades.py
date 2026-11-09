"""Hades — checkpoint / durable restart side-interface for Kin.

Implements Level-1 structural fix from the multi-step agent failure taxonomy:
fresh context across attempts, keep errors inside the attempt, cross the
boundary with a lesson + restorable reference.

Design contracts:
    - The lesson is the only thing that crosses attempts. Full history,
      full evidence, and scars stay inside the attempt that produced them.
    - save() does not gate on verified. The caller (bundle.cycle) gates.
      An unverified checkpoint is written if called directly; it teaches
      nothing, but it also does not lie about being verified (the
      `verified` field records the truth).
    - restore_fresh() never raises on a missing checkpoint. It returns an
      empty fresh ControlPacket so a restart path can always proceed.
    - File-backed by default. `data/hades/<ckpt_id>.json`. Survives
      process restart. Safe to delete the directory; nothing else depends
      on it.

Cross-attempt carries:
    lesson        (str)   — one-line durable summary
    control_state (dict)  — guides_loaded, budget_remaining, confidence,
                            risk_class
    residual_hash (str)   — the residual Packet hash, if any

Cross-attempt drops:
    history               — trajectory stays inside the attempt
    evidence              — full evidence stays inside; only evidence_gist
                            crosses (last 5 entries)
    scars                 — a scarred packet carries its scars; a fresh
                            restart does not
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from resileos.harness.packet import ControlPacket


# ── checkpoint record ────────────────────────────────────────────────


@dataclass
class Checkpoint:
    id: str
    created_at: str
    turn: int
    verified: bool
    residual_packet_hash: Optional[str]
    lesson: str                         # the only thing that should cross attempts
    evidence_gist: list[dict]           # bounded, not full history
    control_state: dict                 # minimal ControlPacket fields
    scars: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "turn": self.turn,
            "verified": self.verified,
            "residual_packet_hash": self.residual_packet_hash,
            "lesson": self.lesson,
            "evidence_gist": self.evidence_gist[-5:],  # keep tiny
            "control_state": self.control_state,
            "scars": self.scars,
        }


# ── store ────────────────────────────────────────────────────────────


class Hades:
    """Process-local checkpoint store. File-backed by default so it survives restart."""

    def __init__(self, store_dir: str | Path = "data/hades") -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Checkpoint] = {}

    def _path(self, ckpt_id: str) -> Path:
        return self.store_dir / f"{ckpt_id}.json"

    # ── save ────────────────────────────────────────────────────
    def save(
        self,
        control: ControlPacket,
        residual_packet_hash: Optional[str] = None,
        lesson: Optional[str] = None,
    ) -> Checkpoint:
        """Create a checkpoint. Lesson is the only thing that should cross attempts.

        Does not gate on `control.verified` — the caller does. If the
        caller wants verified-only checkpoints, it should check
        `control.verified` before calling save().
        """
        if lesson is None:
            recent = control.history[-3:] if control.history else []
            lesson = (
                f"turn {control.turn}: verified={control.verified}, "
                f"scars={len(control.scars or [])}, "
                f"evidence={len(control.evidence or [])}"
            )
            if recent:
                last = recent[-1]
                ev = last.get("event", "none") if isinstance(last, dict) else "none"
                lesson += f" | last_event={ev}"

        # Two saves of the same packet at the same turn produce different
        # ids because of the timestamp. That is deliberate: each verified
        # cycle is its own checkpoint, even if the control state matches.
        ckpt_id = hashlib.sha256(
            f"{control.id}:{control.turn}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:12]

        # Safe attribute access: ControlPacket may not have risk_class or
        # confidence in some builds. getattr with a default avoids
        # AttributeError and lets the checkpoint save proceed.
        control_state = {
            "confidence": getattr(control, "confidence", None),
            "risk_class": getattr(control, "risk_class", None),
            "guides_loaded": list(getattr(control, "guides_loaded", []) or []),
            "budget_remaining": dict(
                getattr(control, "budget_remaining", {}) or {}
            ),
        }

        ckpt = Checkpoint(
            id=ckpt_id,
            created_at=datetime.utcnow().isoformat(),
            turn=int(getattr(control, "turn", 0)),
            verified=bool(getattr(control, "verified", False)),
            residual_packet_hash=residual_packet_hash,
            lesson=lesson,
            evidence_gist=list(getattr(control, "evidence", []) or [])[-5:],
            control_state=control_state,
            scars=list(getattr(control, "scars", []) or [])[:],
        )
        self._cache[ckpt.id] = ckpt
        self._path(ckpt.id).write_text(json.dumps(ckpt.to_dict(), indent=2))
        return ckpt

    # ── load ────────────────────────────────────────────────────
    def load(self, ckpt_id: str) -> Optional[Checkpoint]:
        if ckpt_id in self._cache:
            return self._cache[ckpt_id]
        p = self._path(ckpt_id)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        try:
            ckpt = Checkpoint(**data)
        except TypeError:
            return None
        self._cache[ckpt_id] = ckpt
        return ckpt

    # ── restore ─────────────────────────────────────────────────
    def restore_fresh(
        self,
        ckpt_id: str,
        new_id: Optional[str] = None,
    ) -> ControlPacket:
        """Return a fresh ControlPacket seeded only with the lesson + minimal state.

        Full history, full evidence, and scars from the previous attempt
        are dropped (Level-1 rule: resume the work, not the mistake).

        If the checkpoint is missing, returns an empty fresh packet with
        the caller-supplied id (or "fresh"). Never raises.
        """
        ckpt = self.load(ckpt_id)
        if ckpt is None:
            fresh = ControlPacket(id=new_id or "fresh")
            fresh.verified = False
            return fresh

        fresh = ControlPacket(id=new_id or f"from-{ckpt.id}")
        fresh.guides_loaded = list(
            ckpt.control_state.get("guides_loaded", []) or []
        )
        fresh.budget_remaining = dict(
            ckpt.control_state.get("budget_remaining", {})
            or getattr(fresh, "budget_remaining", {})
        )
        # Explicit: the fresh packet is NOT verified. It must re-verify.
        fresh.verified = False
        # Optional: copy over confidence/risk_class if ControlPacket
        # supports them. Uses setattr so a missing attribute on the
        # dataclass does not crash the restore.
        conf = ckpt.control_state.get("confidence")
        if conf is not None and hasattr(fresh, "confidence"):
            fresh.confidence = conf
        risk = ckpt.control_state.get("risk_class")
        if risk is not None and hasattr(fresh, "risk_class"):
            fresh.risk_class = risk
        # Intentionally do not copy history, full evidence, or scars.
        fresh.append({
            "event": "restored_from_checkpoint",
            "from": ckpt.id,
            "lesson": ckpt.lesson,
            "verified_previous": ckpt.verified,
        })
        return fresh

    # ── inspection ──────────────────────────────────────────────
    def latest(self) -> Optional[Checkpoint]:
        """Most recent checkpoint by file mtime, with created_at tiebreak.

        mtime handles the same-session ordering; created_at handles the
        case where two files are written within the same filesystem tick
        (common in tests).
        """
        files = list(self.store_dir.glob("*.json"))
        if not files:
            return None
        files.sort(
            key=lambda p: (p.stat().st_mtime, p.name),
            reverse=True,
        )
        ckpt = self.load(files[0].stem)
        if ckpt is not None:
            return ckpt
        # Fall back: if the newest file is unreadable, scan for the
        # newest readable one.
        for p in files[1:]:
            ckpt = self.load(p.stem)
            if ckpt is not None:
                return ckpt
        return None

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.store_dir.glob("*.json"))

    def clear(self) -> None:
        """Delete all checkpoint files and drop the cache."""
        for p in self.store_dir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
        self._cache.clear()


# ── convenience factory matching the other Kin side-interfaces ───────


def make_hades(store_dir: str | Path = "data/hades") -> Hades:
    return Hades(store_dir=store_dir)


__all__ = ["Checkpoint", "Hades", "make_hades"]
