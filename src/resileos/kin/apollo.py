"""Apollo kin: golden-ladder improve with healing and next-step.

Healing factor from the suite (~39.5) lifts a rejected hop.
Next-step prediction uses the golden phase to propose the following
hop before it is verified. Art (music, poetry) is kept as a path
that is not required to be pure truth.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.success_improve import hop_weights, phase_hop, keep_verified

# Suite healing factor. Public placeholder; private residual can replace.
HEALING = 39.5


class ApolloKin:
    def __init__(self, subject: str = "world:apollo") -> None:
        self.subject = subject
        self.lifts: list[float] = []
        self.kept: list[dict[str, Any]] = []
        self.predictions: list[dict[str, Any]] = []

    def predict_next(self, hop: dict[str, Any]) -> dict[str, Any]:
        """Prophetic next step from the last phase and golden weight."""
        hops = hop.get("hops", [])
        if not hops:
            return {"phase": 0.0, "weight": 1.0}
        last = hops[-1]
        nxt_weight = hop_weights(1)[0]
        pred = {
            "phase": last.get("phase", 0.0),
            "weight": nxt_weight,
            "note": "next hop predicted from golden ladder",
        }
        self.predictions.append(pred)
        return pred

    def step(
        self,
        facts: list[dict[str, str]],
        *,
        eat_fn: Optional[Callable[..., Any]] = None,
        art: bool = False,
    ) -> dict[str, Any]:
        hop = phase_hop(facts, subject=self.subject)
        pred = self.predict_next(hop)
        lifted = []
        lift = 1.0
        for h in hop["hops"]:
            step = h["step"]
            accepted = True
            if eat_fn is not None and not art:
                claim = f"{step.get('subject')} {step.get('relation')} {step.get('obj')}"
                d = eat_fn(claim)
                accepted = bool(getattr(d, "accepted", False))
            if accepted or art:
                kept = keep_verified(
                    {"subject": self.subject, "hops": [h]},
                    eat_fn=None if art else eat_fn,
                )
                for k in kept:
                    k["weight"] = k["weight"] * lift
                    k["healing"] = HEALING if lift > 1.0 else 1.0
                    self.kept.append(k)
                    lifted.append(k)
                lift = 1.0
            else:
                lift *= 1.0 + abs(h["weight"]) / HEALING
                self.lifts.append(lift)
        return {
            "subject": self.subject,
            "hops": hop["n"],
            "kept": len(lifted),
            "facts": lifted,
            "lifts": list(self.lifts),
            "prediction": pred,
            "art": art,
            "healing": HEALING,
            "note": "Failure lifts by the healing factor. Art skips pure-truth gate.",
        }


def apollo_cycle(
    facts: list[dict[str, str]],
    *,
    subject: str = "world:apollo",
    eat_fn: Optional[Callable[..., Any]] = None,
    art: bool = False,
) -> dict[str, Any]:
    return ApolloKin(subject).step(facts, eat_fn=eat_fn, art=art)
