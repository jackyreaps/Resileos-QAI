"""Typed results for one Demi-god duty."""
from __future__ import annotations

from dataclasses import dataclass

# Stable Momus codes. NEED_MORE is not approval.
NEED_MISSING_REQUIREMENT = "missing_requirement"
NEED_MISSING_RESIDUAL_HASH = "missing_residual_hash"
NEED_MISSING_SPEC_FIELD = "missing_spec_field"

OUTCOME_APPROVED = "approved"
OUTCOME_FAIL = "fail"
OUTCOME_NEED_MORE = "need_more"


@dataclass(frozen=True)
class Defect:
    """One mismatch found by a blind review."""

    location: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "location": self.location,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True)
class NeedMore:
    """Something Momus cannot check because it was not supplied."""

    code: str
    location: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "location": self.location,
            "message": self.message,
        }


@dataclass(frozen=True)
class DemigodResult:
    """verified/success, a reason, and the evidence the check actually used.

    ``verified`` and ``success`` are true only for outcome ``approved``.
    ``need_more`` lists missing inputs. That outcome is never approval.
    """

    demigod: str
    verified: bool
    success: bool
    reason: str
    evidence: tuple[dict, ...] = ()
    defects: tuple[Defect, ...] = ()
    outcome: str = OUTCOME_FAIL
    need_more: tuple[NeedMore, ...] = ()

    def to_dict(self) -> dict:
        return {
            "demigod": self.demigod,
            "verified": self.verified,
            "success": self.success,
            "reason": self.reason,
            "outcome": self.outcome,
            "evidence": [dict(item) for item in self.evidence],
            "defects": [item.to_dict() for item in self.defects],
            "need_more": [item.to_dict() for item in self.need_more],
        }


def finish(
    demigod: str,
    ok: bool,
    reason: str,
    evidence: list[dict] | tuple[dict, ...],
    defects: list[Defect] | tuple[Defect, ...] = (),
    *,
    outcome: str | None = None,
    need_more: list[NeedMore] | tuple[NeedMore, ...] = (),
) -> DemigodResult:
    needs = tuple(need_more)
    if outcome is None:
        outcome = OUTCOME_APPROVED if ok and not needs else OUTCOME_FAIL
    # A need-more list is never an approval, even if the caller said ok.
    if needs and outcome == OUTCOME_APPROVED:
        outcome = OUTCOME_NEED_MORE
    approved = outcome == OUTCOME_APPROVED and not needs and bool(ok)
    return DemigodResult(
        demigod=demigod,
        verified=approved,
        success=approved,
        reason=reason,
        evidence=tuple(dict(item) for item in evidence),
        defects=tuple(defects),
        outcome=OUTCOME_APPROVED if approved else outcome,
        need_more=needs,
    )
