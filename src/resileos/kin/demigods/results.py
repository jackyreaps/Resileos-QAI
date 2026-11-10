"""Typed results for one Demi-god duty."""
from __future__ import annotations

from dataclasses import dataclass


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
class DemigodResult:
    """verified/success, a reason, and the evidence the check actually used.

    ``verified`` and ``success`` are the same boolean. Themis and
    Hephaestus speak in verified; Nike speaks in success; Momus uses
    verified for approval. Both fields are set so callers can read either.
    """

    demigod: str
    verified: bool
    success: bool
    reason: str
    evidence: tuple[dict, ...] = ()
    defects: tuple[Defect, ...] = ()

    def to_dict(self) -> dict:
        return {
            "demigod": self.demigod,
            "verified": self.verified,
            "success": self.success,
            "reason": self.reason,
            "evidence": [dict(item) for item in self.evidence],
            "defects": [item.to_dict() for item in self.defects],
        }


def finish(
    demigod: str,
    ok: bool,
    reason: str,
    evidence: list[dict] | tuple[dict, ...],
    defects: list[Defect] | tuple[Defect, ...] = (),
) -> DemigodResult:
    return DemigodResult(
        demigod=demigod,
        verified=bool(ok),
        success=bool(ok),
        reason=reason,
        evidence=tuple(dict(item) for item in evidence),
        defects=tuple(defects),
    )
