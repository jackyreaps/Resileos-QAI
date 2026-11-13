"""Frame reflection for individual → hub → latent.

Structure follows the Frame Atlas drafts (owner, unpublished): a frame
has axes, a verdict space, a scope, and non-claims. Dimensionality,
level, openness, and genealogy are reported separately and are not a
score. More axes or levels are not truer.

The meta-aware root recognizes a frame, keeps axes distinct until a
stated reason combines them, states non-claims, may abstain without
counting that as failure, and applies those tests to itself. Gnosis is
still unfilled. This module does not import it, Titanos, or ResidualCore.
"""
from __future__ import annotations

from dataclasses import dataclass

# Kept distinct on every stored tier. Promotion may not merge these
# unless the caller states a reason.
TIER_AXES = ("statement", "source", "limit")

VERDICT_SPACE = ("accept", "abstain", "refuse")

_SHARED_NON_CLAIMS = (
    "does not verify a user statement as a world fact",
    "does not rank users",
    "does not score beliefs",
    "does not treat more axes or levels as truer",
)

_REFUSAL = frozenset({"abstain", "refuse", "ABSTAINED"})


@dataclass(frozen=True)
class Openness:
    """Whether the frame can be shown wrong, and how."""

    open: bool
    how: str

    def to_dict(self) -> dict[str, object]:
        return {"open": self.open, "how": self.how}


@dataclass(frozen=True)
class StoredFrame:
    """One named frame. Properties are siblings, not a combined score."""

    name: str
    tier: str
    axes: tuple[str, ...]
    verdict_space: tuple[str, ...]
    scope: str
    non_claims: tuple[str, ...]
    level: int
    genealogy: str
    openness: Openness

    @property
    def dimensionality(self) -> int:
        return len(self.axes)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "tier": self.tier,
            "axes": list(self.axes),
            "verdict_space": list(self.verdict_space),
            "scope": self.scope,
            "non_claims": list(self.non_claims),
            "dimensionality": self.dimensionality,
            "level": self.level,
            "openness": self.openness.to_dict(),
            "genealogy": self.genealogy,
            "scores_beliefs": False,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "StoredFrame":
        openness = raw.get("openness") or {}
        if not isinstance(openness, dict):
            openness = {}
        return cls(
            name=str(raw.get("name") or ""),
            tier=str(raw.get("tier") or ""),
            axes=tuple(str(item) for item in (raw.get("axes") or [])),
            verdict_space=tuple(str(item) for item in (raw.get("verdict_space") or [])),
            scope=str(raw.get("scope") or ""),
            non_claims=tuple(str(item) for item in (raw.get("non_claims") or [])),
            level=int(raw.get("level") or 0),
            genealogy=str(raw.get("genealogy") or ""),
            openness=Openness(
                open=bool(openness.get("open")),
                how=str(openness.get("how") or ""),
            ),
        )


def _open(how: str) -> Openness:
    return Openness(open=True, how=how)


def root_frame() -> StoredFrame:
    """The meta-aware root, checked by the same tests as every other frame."""
    return StoredFrame(
        name="meta-aware-root",
        tier="root",
        axes=(
            "recognizes frames as frames",
            "keeps axes distinct until a stated reason forces combining them",
            "states non-claims",
            "may abstain without counting that as failure",
            "applies the same tests to itself",
        ),
        verdict_space=VERDICT_SPACE,
        scope="frame reflection from an individual residual to a guild hub to the latent seed",
        non_claims=_SHARED_NON_CLAIMS + ("does not settle gnosis",),
        level=0,
        genealogy="this is the meta-aware root",
        openness=_open(
            "a promotion that merges axes without a stated reason, drops a non-claim, "
            "or closes an open frame is refused"
        ),
    )


def latent_frame() -> StoredFrame:
    return StoredFrame(
        name="resileos-self",
        tier="latent",
        axes=TIER_AXES,
        verdict_space=VERDICT_SPACE,
        scope="the verified self-facts seed and recurring shared residuals",
        non_claims=_SHARED_NON_CLAIMS
        + (
            "does not publish personal facts to latent",
            "does not claim frontier model performance",
            "does not invent a video url",
        ),
        level=1,
        genealogy="under the meta-aware root; the shared seed above guild hubs",
        openness=_open("a seed needle that is missing from its check file shows this frame wrong"),
    )


def hub_frame(guild_id: str) -> StoredFrame:
    return StoredFrame(
        name=f"hub:{guild_id}",
        tier="hub",
        axes=TIER_AXES,
        verdict_space=VERDICT_SPACE,
        scope=f"residuals seated members of org:guild:{guild_id} opted to share",
        non_claims=_SHARED_NON_CLAIMS + ("does not publish personal facts to latent",),
        level=2,
        genealogy="under the latent seed and the meta-aware root; one chartered guild",
        openness=_open("a seated member can leave the residual unpromoted, and personal facts stay off latent"),
    )


def individual_frame(individual_id: str) -> StoredFrame:
    return StoredFrame(
        name=f"individual:{individual_id}",
        tier="individual",
        axes=TIER_AXES,
        verdict_space=VERDICT_SPACE,
        scope="statements this person made",
        non_claims=_SHARED_NON_CLAIMS,
        level=3,
        genealogy="under the hub when seated, otherwise under the latent seed; under the meta-aware root",
        openness=_open("the person can edit or delete the statement, and a missing statement abstains"),
    )


class MetaAwareRoot:
    """Five duties. Abstain is not a failure. Nothing here ranks a person."""

    def recognize(self, frame: StoredFrame) -> dict[str, object]:
        """A frame stays a frame only while it is named, limited, and correctable."""
        named = bool(frame.name.strip())
        limited = bool(frame.scope.strip()) and bool(frame.non_claims)
        can_refuse = any(item in _REFUSAL for item in frame.verdict_space)
        correctable = bool(frame.openness.open) and bool(frame.openness.how.strip())
        is_frame = named and limited and can_refuse and correctable
        return {
            "recognizes_frame": is_frame,
            "is_frame": is_frame,
            "named": named,
            "limited": limited,
            "correctable": correctable,
            "can_refuse": can_refuse,
        }

    def axes_stay_distinct(self, frame: StoredFrame, *, axis_merge_reason: str = "") -> dict[str, object]:
        """Axes stay listed apart. A reason is required before any combine."""
        return {
            "axes": list(frame.axes),
            "distinct": not str(axis_merge_reason or "").strip(),
            "axis_merge_reason": str(axis_merge_reason or "").strip(),
        }

    def state_non_claims(self, frame: StoredFrame) -> list[str]:
        return list(frame.non_claims)

    def abstain(self, reason: str) -> dict[str, object]:
        return {
            "status": "ABSTAINED",
            "failure": False,
            "reason": reason,
            "scores_beliefs": False,
        }

    def collapse(
        self,
        lower: StoredFrame,
        proposed: StoredFrame,
        *,
        axis_merge_reason: str = "",
    ) -> dict[str, object]:
        """Refuse an upward step that collapses the lower frame.

        Merging axes needs a stated reason. Non-claims may not disappear.
        An open frame may not become closed. Refusal abstains and is not
        a failure. Dimensionality and level are not compared as truth.
        """
        reason = str(axis_merge_reason or "").strip()
        missing = [axis for axis in lower.axes if axis not in proposed.axes]
        merged = bool(missing)
        merge_without_reason = merged and not reason
        dropped = [claim for claim in lower.non_claims if claim not in proposed.non_claims]
        closed = bool(lower.openness.open) and not proposed.openness.open
        refused = merge_without_reason or bool(dropped) or closed
        if refused and merge_without_reason:
            why = "axes merged without a stated reason"
        elif refused and dropped:
            why = "non-claims dropped"
        elif refused and closed:
            why = "open frame closed"
        else:
            why = ""
        return {
            "refused": refused,
            "abstain": refused,
            "failure": False,
            "status": "ABSTAINED" if refused else "ACCEPTED",
            "reason": why,
            "merged_axes": merged,
            "axis_merge_reason": reason,
            "missing_axes": missing,
            "dropped_non_claims": dropped,
            "closed_an_open_frame": closed,
            "dimensionality": {
                "lower": lower.dimensionality,
                "proposed": proposed.dimensionality,
            },
            "level": {"lower": lower.level, "proposed": proposed.level},
            "scores_beliefs": False,
        }

    def self_check(self) -> dict[str, object]:
        """The root applies recognize, non-claims, and collapse to itself."""
        own = root_frame()
        recognized = self.recognize(own)
        collapsed = self.collapse(own, own)
        return {
            "frame": own.to_dict(),
            "recognized": recognized,
            "non_claims": self.state_non_claims(own),
            "axes": self.axes_stay_distinct(own),
            "collapse": collapsed,
            "abstain": self.abstain("the root can abstain"),
            "failure": False,
            "scores_beliefs": False,
        }


@dataclass(frozen=True)
class ReflectionVerdict:
    recurring: bool
    holders: int
    reason: str
    gnosis: str = "unfilled"
    status: str = "ACCEPTED"
    failure: bool = False
    collapse: dict | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "recurring": self.recurring,
            "holders": self.holders,
            "reason": self.reason,
            "gnosis": self.gnosis,
            "status": self.status,
            "failure": self.failure,
            "collapse": self.collapse,
            "descriptive": True,
            "scores_beliefs": False,
        }


class FrameReflection:
    """Count a recurring residual, then run the root's collapse check.

    ``holders`` is how many members stated the same text. It is not a rank
    and it is not a belief score. ``gnosis`` stays ``unfilled``.
    """

    def __init__(self, min_holders: int = 2) -> None:
        self.min_holders = max(2, int(min_holders))
        self.root = MetaAwareRoot()

    def recurring(self, texts: list[str], candidate: str) -> ReflectionVerdict:
        needle = candidate.strip()
        holders = sum(1 for text in texts if text.strip() == needle)
        enough = bool(needle) and holders >= self.min_holders
        reason = "count" if enough else "below-min-holders"
        return ReflectionVerdict(
            recurring=enough,
            holders=holders,
            reason=reason,
            gnosis="unfilled",
            status="ACCEPTED" if enough else "ABSTAINED",
            failure=False,
        )

    def gate(
        self,
        lower: StoredFrame,
        proposed: StoredFrame,
        *,
        axis_merge_reason: str = "",
    ) -> dict[str, object]:
        """Abstain when the proposed frame is not a frame or collapses the lower one."""
        recognized = self.root.recognize(proposed)
        lower_ok = self.root.recognize(lower)
        collapsed = self.root.collapse(
            lower, proposed, axis_merge_reason=axis_merge_reason
        )
        abstain = (not recognized["is_frame"]) or (not lower_ok["is_frame"]) or bool(
            collapsed["refused"]
        )
        reason = str(collapsed.get("reason") or "")
        if not recognized["is_frame"]:
            reason = reason or "proposed frame is not named, limited, and correctable"
        if not lower_ok["is_frame"]:
            reason = reason or "lower frame is not named, limited, and correctable"
        return {
            "abstain": abstain,
            "failure": False,
            "status": "ABSTAINED" if abstain else "ACCEPTED",
            "reason": reason,
            "recognized": recognized,
            "collapse": collapsed,
            "scores_beliefs": False,
            "descriptive": True,
            "gnosis": "unfilled",
        }
