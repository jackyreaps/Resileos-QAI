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
    budget_remaining: Dict[str, float] = field(default_factory=lambda: {"steps": 50, "cost": 5.0, "tokens": 120000})
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    scars: List[str] = field(default_factory=list)  # residual scars / constraints applied
    history: List[Dict[str, Any]] = field(default_factory=list)  # log-as-queue
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

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
            "budget_remaining": self.budget_remaining,
            "evidence": self.evidence,
            "scars": self.scars,
            "history": self.history[-20:],  # keep recent for context
        }
