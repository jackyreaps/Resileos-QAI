"""Extended control packet with harness fields.
Drop into or merge with your existing packet contract."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

@dataclass
class ControlPacket:
    """Layered interface between residual core and harness/tools."""
    id: str
    turn: int = 0
    state: Dict[str, Any] = field(default_factory=dict)
    # Harness additions (from paper + Jev + AgenC)
    confidence: Optional[float] = None
    risk_class: Optional[str] = None  # "allow" | "ask" | "deny"
    verified: bool = False
    guides_loaded: List[str] = field(default_factory=list)
    # Bounded guide text keyed by the same id stored in guides_loaded.
    # Same object is shared through to_dict() so in-place edits persist.
    guide_bodies: Dict[str, str] = field(default_factory=dict)
    budget_remaining: Dict[str, float] = field(default_factory=lambda: {"steps": 50, "cost": 5.0, "tokens": 120000})
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    scars: List[str] = field(default_factory=list)  # residual scars / constraints applied
    history: List[Dict[str, Any]] = field(default_factory=list)  # log-as-queue
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Optional 5-pin cascade address. Recorded only; not a verify gate.
    pin: Optional[str] = None
    address: Optional[Dict[str, Any]] = None

    def append(self, event: Dict[str, Any]) -> None:
        self.history.append({**event, "ts": datetime.utcnow().isoformat()})
        self.turn += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "turn": self.turn,
            "state": self.state,
            "confidence": self.confidence,
            "risk_class": self.risk_class,
            "verified": self.verified,
            "guides_loaded": self.guides_loaded,
            "guide_bodies": self.guide_bodies,
            "budget_remaining": self.budget_remaining,
            "evidence": self.evidence,
            "scars": self.scars,
            "history": self.history[-20:],  # keep recent for context
            "pin": self.pin,
            "address": dict(self.address) if self.address is not None else None,
        }


_PROVIDER_STAGES = ("draft", "verify", "upscale")


@dataclass
class VideoPacket(ControlPacket):
    """Control packet for one clip or one scene step.

    ``frame_residuals`` are packet hashes, not pixels. ``scene_script_hash``
    is the hash of a scene artifact when a scene legion wrote one. The
    script source does not live on this packet.
    """

    frame_residuals: List[str] = field(default_factory=list)
    temporal_delta: float = 0.0
    keyframe_ids: List[int] = field(default_factory=list)
    provider_stage: str = "draft"
    scene_script_hash: Optional[str] = None
    # Recorded check metrics (studio.clip_metrics). Not a verify gate.
    check_metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider_stage not in _PROVIDER_STAGES:
            self.provider_stage = "draft"
        self.frame_residuals = [str(item) for item in self.frame_residuals]
        self.keyframe_ids = [int(item) for item in self.keyframe_ids]
        self.temporal_delta = float(self.temporal_delta)
        if self.scene_script_hash is not None:
            self.scene_script_hash = str(self.scene_script_hash)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["frame_residuals"] = list(self.frame_residuals)
        data["temporal_delta"] = self.temporal_delta
        data["keyframe_ids"] = list(self.keyframe_ids)
        data["provider_stage"] = self.provider_stage
        data["scene_script_hash"] = self.scene_script_hash
        data["check_metrics"] = dict(self.check_metrics)
        return data
