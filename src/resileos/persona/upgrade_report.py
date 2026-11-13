"""Operator-facing upgrade proposals from verified dream candidates.

Proposals are split into two tiers:

- Auto: only the explicit allowlist of bounded operational state
  (tool weights, search/crawl cache, source-quality ranking, metric
  thresholds and tuning params). These may apply through
  ``OperationalStore``, are versioned and metric-gated, and auto-revert
  if the gated metric gets worse. Every change is logged here.
- Review: everything else (new modules, schema changes, learning or
  Eat changes, values outside bounds, unknown targets). These stay
  ``pending`` until a human approves them. An approved proposal
  becoming a PR is out of scope; that step is documented, not run.

Classification uses the allowlist and defaults to review. This module
never modifies code or config files, never calls Eat, learn, or
Titanos, and never touches the scar matrix, ``require_verified``, or
the Metis defaults.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from resileos.persona.operational_tune import AUTO_TARGETS, OperationalStore, in_bounds

PROPOSAL_KINDS = ("tighter_method", "new_module", "schema_change")
# Kinds that can never auto-apply, even if the target is on the allowlist.
REVIEW_KINDS = frozenset({"new_module", "schema_change"})
PROPOSAL_STATUSES = ("pending", "auto_applied", "auto_reverted", "approved", "rejected")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify(
    kind: str,
    target: str,
    value: Any | None = None,
) -> str:
    """Return ``auto`` or ``review``. Unknown targets default to review."""
    if kind not in PROPOSAL_KINDS or kind in REVIEW_KINDS:
        return "review"
    if target not in AUTO_TARGETS:
        return "review"
    if value is not None and not in_bounds(target, value):
        return "review"
    return "auto"


def proposal_from_candidate(
    candidate: dict[str, Any],
    *,
    kind: str,
    target: str,
    value: Any | None = None,
) -> dict[str, Any]:
    """Build one structured proposal. Status is pending until classified."""
    if kind not in PROPOSAL_KINDS:
        kind = "schema_change"
    evidence = {
        "fingerprint": candidate.get("fingerprint"),
        "aggregate": candidate.get("aggregate") or candidate.get("evidence") or {},
        "residual_gain": candidate.get("improvement") or candidate.get("residual_gain") or 0.0,
        "error": candidate.get("error"),
        "scar": candidate.get("scar"),
        "factor_count": candidate.get("factor_count"),
        "count": candidate.get("count"),
    }
    tier = classify(kind, target, value)
    return {
        "kind": kind,
        "target": target,
        "tier": tier,
        "evidence": evidence,
        "verification_status": "verified" if candidate.get("verified") else "unverified",
        "proposal_status": "pending",
        "value": value,
        "created_at": _now(),
        "writes_code": False,
        "writes_config": False,
        "writes_titanos": False,
        "learned": False,
    }


class UpgradeReport:
    """JSON log of proposals and auto-tier changes, plus a markdown view."""

    def __init__(self) -> None:
        self.proposals: list[dict[str, Any]] = []
        self.auto_log: list[dict[str, Any]] = []

    def add(self, proposal: dict[str, Any]) -> dict[str, Any]:
        item = dict(proposal)
        item.setdefault("proposal_status", "pending")
        if not item.get("id"):
            seed = json.dumps(
                {
                    "kind": item.get("kind"),
                    "target": item.get("target"),
                    "created_at": item.get("created_at"),
                    "n": len(self.proposals),
                },
                sort_keys=True,
            )
            item["id"] = "p-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        self.proposals.append(item)
        return item

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "UpgradeReport":
        report = cls()
        payload = data or {}
        report.proposals = [dict(item) for item in payload.get("proposals") or []]
        report.auto_log = [dict(item) for item in payload.get("auto_log") or []]
        return report

    def approve(self, proposal_id: str, *, actor: str = "") -> dict[str, Any]:
        """Mark a proposal approved for a later PR. Never applies code."""
        return self._decide(proposal_id, "approved", actor)

    def reject(self, proposal_id: str, *, actor: str = "") -> dict[str, Any]:
        """Mark a proposal rejected. Never applies or reverts code here."""
        return self._decide(proposal_id, "rejected", actor)

    def _decide(self, proposal_id: str, status: str, actor: str) -> dict[str, Any]:
        for item in self.proposals:
            if item.get("id") != proposal_id:
                continue
            item["proposal_status"] = status
            item["decided_at"] = _now()
            if actor:
                item["decided_by"] = actor
            item["applied_on_approve"] = False
            item["writes_code"] = False
            item["writes_config"] = False
            item["writes_titanos"] = False
            item["learned"] = False
            return {"ok": True, "applied": False, "proposal": item}
        return {"ok": False, "applied": False, "reason": "unknown proposal"}

    def log_auto(self, record: dict[str, Any]) -> None:
        self.auto_log.append(dict(record))

    def emit(
        self,
        candidate: dict[str, Any],
        *,
        kind: str,
        target: str,
        value: Any | None = None,
        store: OperationalStore | None = None,
        metric_name: str = "",
        metric_before: float | None = None,
    ) -> dict[str, Any]:
        """Record a proposal. Auto-tier items may apply on the store.

        Unverified candidates are recorded as pending review and are
        never auto-applied. Applying still does not touch Eat, learn,
        scars, or Titanos.
        """
        proposal = proposal_from_candidate(
            candidate, kind=kind, target=target, value=value
        )
        if proposal["verification_status"] != "verified":
            proposal["tier"] = "review"
            proposal["proposal_status"] = "pending"
            proposal["reason"] = "unverified candidates stay on the review tier"
            return self.add(proposal)
        if proposal["tier"] == "auto" and store is not None and value is not None:
            key = str((proposal.get("evidence") or {}).get("fingerprint") or target)
            result = store.apply(
                target=target,
                key=key,
                value=value,
                metric_name=metric_name or "residual_gain",
                metric_before=float(
                    metric_before
                    if metric_before is not None
                    else proposal["evidence"].get("residual_gain") or 0.0
                ),
                report=self,
            )
            if result.get("applied"):
                proposal["proposal_status"] = "auto_applied"
                proposal["version"] = result["version"]
            else:
                proposal["tier"] = "review"
                proposal["proposal_status"] = "pending"
                proposal["reason"] = result.get("reason") or "auto apply refused"
        return self.add(proposal)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposals": list(self.proposals),
            "auto_log": list(self.auto_log),
            "writes_code": False,
            "writes_config": False,
            "writes_titanos": False,
            "learned": False,
            "approved_to_pr": "out of scope: a human-approved review item becomes a normal PR",
            "email_digest": "future: optional daily digest once email sending is configured",
        }

    def to_markdown(self) -> str:
        """Readable summary for an operator."""
        lines = ["# Upgrade proposals", ""]
        if not self.proposals and not self.auto_log:
            lines.append("No proposals.")
            return "\n".join(lines) + "\n"
        for item in self.proposals:
            evidence = item.get("evidence") or {}
            lines.append(f"- **{item.get('kind')}** on `{item.get('target')}`")
            lines.append(f"  - tier: {item.get('tier')}")
            lines.append(f"  - verification: {item.get('verification_status')}")
            lines.append(f"  - status: {item.get('proposal_status')}")
            lines.append(f"  - residual gain: {evidence.get('residual_gain')}")
            lines.append(f"  - fingerprint: {evidence.get('fingerprint')}")
        if self.auto_log:
            lines.append("")
            lines.append("## Auto-tier log")
            for record in self.auto_log:
                lines.append(
                    f"- v{record.get('version')} {record.get('target')}"
                    f"[{record.get('key')}] status={record.get('status')}"
                    f" reverted={record.get('reverted')}"
                )
        lines.append("")
        lines.append(
            "Approved review-tier proposals become a normal PR; "
            "that step is not run from this report."
        )
        return "\n".join(lines) + "\n"
