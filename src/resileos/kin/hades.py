"""Hades — checkpoint / durable restart side-interface for Kin.

Implements Level-1 structural fix from the multi-step agent failure taxonomy:
fresh context across attempts, keep errors inside the attempt, cross the
boundary with a lesson + restorable reference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import json
import hashlib

from resileos.harness.packet import ControlPacket


@dataclass
class Checkpoint:
    id: str
    created_at: str
    turn: int
    verified: bool
    residual_packet_hash: Optional[str]
    lesson: str                          # the only thing that should cross attempts
    evidence_gist: list[dict]            # bounded, not full history
    control_state: dict                  # minimal ControlPacket fields
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


class Hades:
    """Process-local checkpoint store. File-backed by default so it survives restart."""

    def __init__(self, store_dir: str | Path = "data/hades"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Checkpoint] = {}

    def _path(self, ckpt_id: str) -> Path:
        return self.store_dir / f"{ckpt_id}.json"

    def save(
        self,
        control: ControlPacket,
        residual_packet_hash: Optional[str] = None,
        lesson: Optional[str] = None,
    ) -> Checkpoint:
        """Create a checkpoint. Lesson is the only thing that should cross attempts."""
        if lesson is None:
            # Cheap extraction: last verified note or a one-line summary
            recent = control.history[-3:] if control.history else []
            lesson = (
                f"turn {control.turn}: verified={control.verified}, "
                f"scars={len(control.scars)}, evidence={len(control.evidence)}"
            )
            if recent:
                lesson += f" | last_event={recent[-1].get('event', 'none')}"

        ckpt = Checkpoint(
            id=hashlib.sha256(f"{control.id}:{control.turn}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12],
            created_at=datetime.utcnow().isoformat(),
            turn=control.turn,
            verified=control.verified,
            residual_packet_hash=residual_packet_hash,
            lesson=lesson,
            evidence_gist=control.evidence[-5:] if control.evidence else [],
            control_state={
                "confidence": control.confidence,
                "risk_class": control.risk_class,
                "guides_loaded": control.guides_loaded,
                "budget_remaining": control.budget_remaining,
            },
            scars=control.scars[:],
        )
        self._cache[ckpt.id] = ckpt
        self._path(ckpt.id).write_text(json.dumps(ckpt.to_dict(), indent=2))
        return ckpt

    def load(self, ckpt_id: str) -> Optional[Checkpoint]:
        if ckpt_id in self._cache:
            return self._cache[ckpt_id]
        p = self._path(ckpt_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        ckpt = Checkpoint(**data)
        self._cache[ckpt_id] = ckpt
        return ckpt

    def restore_fresh(self, ckpt_id: str, new_id: Optional[str] = None) -> ControlPacket:
        """Return a *fresh* ControlPacket seeded only with the lesson + minimal state.
        Full history and scars from the previous attempt are dropped (Level-1 rule).
        """
        ckpt = self.load(ckpt_id)
        if ckpt is None:
            return ControlPacket(id=new_id or "fresh")

        fresh = ControlPacket(id=new_id or f"from-{ckpt.id}")
        fresh.guides_loaded = ckpt.control_state.get("guides_loaded", [])
        fresh.budget_remaining = ckpt.control_state.get("budget_remaining", fresh.budget_remaining)
        fresh.confidence = ckpt.control_state.get("confidence")
        fresh.risk_class = ckpt.control_state.get("risk_class")
        # Intentionally do *not* copy history, full evidence, or scars
        fresh.append({
            "event": "restored_from_checkpoint",
            "from": ckpt.id,
            "lesson": ckpt.lesson,
            "verified_previous": ckpt.verified,
        })
        return fresh

    def latest(self) -> Optional[Checkpoint]:
        files = sorted(self.store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        return self.load(files[0].stem)


# Convenience factory matching the other Kin side-interfaces
def make_hades(store_dir: str | Path = "data/hades") -> Hades:
    return Hades(
