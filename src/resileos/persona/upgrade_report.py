"""Operator-facing upgrade proposals from verified dream candidates.

Proposals are split into tiers (and an L0 refusal, below):

- Auto: only the explicit allowlist of bounded operational state
  (tool weights, search/crawl cache, source-quality ranking, metric
  thresholds and tuning params). These may apply through
  ``OperationalStore``, are versioned and metric-gated, and auto-revert
  if the gated metric gets worse. Every change is logged here.
- Review: everything else (new modules, schema changes, learning or
  Eat changes, values outside bounds, unknown targets). These stay
  ``pending`` until a human approves them. An approved proposal
  becoming a PR is out of scope; that step is documented, not run.

Every proposal is also checked against the harness level registry
(``LEVELS`` below). The harness is leveled:

- L0, protected substrate: the residual core math, the Packet schema and
  hash, Zeus approval, ``require_verified``, residual consistency, the
  Hades lesson-only rule, and the abstain / NO_ROWS / CONFLICT meanings.
  Never rewritten by a proposal: anything touching L0 is ``refused``.
- L1, engines: Kin roles, demi-gods, legions, the cascade router, risk
  rules, SeparatedCycle, budget and scar accounting, ControlPacket
  policy. Review only, after a held-out eval and admin approval. Never
  auto-applied.
- L2, outer matcher: guides, thresholds, lesson extraction, telemetry,
  UI chips, routing heuristics, eval reporting. Only the L2 allowlisted
  operational params may auto-apply, versioned, metric-gated, and
  auto-reverted, including when an L0 or L1 metric on the held-out
  suite gets worse (``guard_l2``).

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
PROPOSAL_STATUSES = ("pending", "auto_applied", "auto_reverted", "approved", "rejected", "refused")

# ── Harness level registry ──────────────────────────────────────────────
# Dotted module, or ``module:symbol``, -> level. The longest matching
# module prefix wins. A symbol can sit at a deeper level than its module
# (Zeus approval is L0 inside the L1 SeparatedCycle module): a proposal
# naming the whole module file counts as touching its L0 symbols, so it
# must name the symbol (``module:Symbol``) to stay at L1. Anything not
# listed is treated as L1: review only, never auto.
L0, L1, L2 = 0, 1, 2
LEVEL_NAMES = {L0: "L0 protected substrate", L1: "L1 engines", L2: "L2 outer matcher"}
LEVELS: dict[str, int] = {
    # L0: protected substrate. Never rewritten by a proposal.
    "resileos.core": L0,                                   # residual core math
    "resileos.packet": L0,                                 # Packet schema and packet_hash
    "resileos.harness.separated:zeus_head": L0,            # Zeus approval
    "resileos.kin.mouth_policy": L0,                       # require_verified
    "resileos.verify": L0,                                 # require_verified (Lean)
    "resileos.harness.tools:residual_consistency": L0,     # residual consistency
    "resileos.harness.tools:verify_on_stop": L0,           # verified needs raw evidence
    "resileos.kin.hades": L0,                              # lesson-only rule
    "resileos.abstention": L0,                             # abstain meaning
    "resileos.chat.router:NO_ROWS": L0,                    # NO_ROWS meaning
    "resileos.chat.router:CONFLICT": L0,                   # CONFLICT meaning
    # L1: engines. Review only, after held-out eval and admin approval.
    "resileos.kin": L1,                                    # Kin roles
    "resileos.kin.demigods": L1,                           # demi-gods
    "resileos.kin.legions": L1,                            # legions
    "resileos.kin.outer_legions": L1,
    "resileos.harness.legions": L1,
    "resileos.harness.cascade": L1,                        # cascade router
    "resileos.harness.tools:risk_classify": L1,            # risk rules
    "resileos.harness.tools:budget_and_stuck_guard": L1,   # budget accounting
    "resileos.harness.separated": L1,                      # SeparatedCycle
    "resileos.harness.packet": L1,                         # ControlPacket policy
    "resileos.persona.residual_factors": L1,               # scar accounting
    # L2: outer matcher. Bounded plasticity, scored on the held-out suite.
    "resileos.kin.demigods.guides": L2,                    # guides
    "resileos.harness.tools:confidence_route": L2,         # routing thresholds
    "resileos.harness.tools:guide_load": L2,
    "resileos.chat.router": L2,                            # routing heuristics
    "resileos.kin.lesson_store": L2,                       # lesson extraction
    "resileos.run_trace": L2,                              # telemetry
    "resileos.kin.iris_trace": L2,
    "scripts.harness_equal_budget": L2,                    # eval reporting (held-out suite)
    "landing.public.assets.chat-ui": L2,                   # UI chips
    "landing.public.assets.stream-parts": L2,
}
# Operational targets: the only L2 params the auto tier may touch.
for _target in AUTO_TARGETS:
    LEVELS["param." + _target] = L2


def _dotted(path: str) -> str:
    """``src/resileos/kin/hades.py`` or ``resileos/kin/hades.py`` -> ``resileos.kin.hades``."""
    raw = str(path or "").strip().replace("\\", "/")
    if raw.startswith("src/"):
        raw = raw[4:]
    for ext in (".py", ".js", ".md"):
        if raw.endswith(ext):
            raw = raw[: -len(ext)]
    raw = raw.replace("/", ".").strip(".")
    if raw.endswith(".__init__"):
        raw = raw[: -len(".__init__")]
    return raw


def level_of(path: str) -> int:
    """The harness level of a module, ``module:symbol``, file path, or ``param.<target>``.

    Longest-prefix match on the registry; unlisted paths are L1 (review).
    A whole module that holds a registered L0 symbol counts as L0.
    """
    raw = str(path or "").strip()
    module, _, symbol = raw.partition(":")
    name = _dotted(module)
    if symbol and f"{name}:{symbol}" in LEVELS:
        return LEVELS[f"{name}:{symbol}"]
    best, level = "", L1
    for key, lv in LEVELS.items():
        if ":" in key:
            continue
        if name == key or name.startswith(key + "."):
            if len(key) > len(best):
                best, level = key, lv
    if not symbol and any(k.startswith(name + ":") and lv == L0 for k, lv in LEVELS.items()):
        return L0
    return level


def proposal_level(target: str, paths: Any = None) -> int:
    """Deepest (lowest) level among the target and every touched path."""
    names = [f"param.{target}" if target in AUTO_TARGETS else str(target or "")]
    names += [str(p) for p in (paths or []) if str(p).strip()]
    levels = [level_of(n) for n in names if n]
    return min(levels) if levels else L1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Coherence metrics and the level each one protects. An L2 change must
# not lower any of these on the held-out suite.
COHERENCE_METRICS: dict[str, int] = {
    "residual_consistency": L0,
    "verification_rate": L0,
    "correct_abstention": L1,
    "budget_efficiency": L1,
}


def guard_l2(before: dict[str, float], after: dict[str, float], *, tol: float = 1e-9) -> dict[str, Any]:
    """Did an L2 change degrade any L0/L1 coherence metric on the held-out suite?

    ``degraded`` lists every guarded metric that is lower after (or
    missing after). An empty list means the change may stay.
    """
    degraded = []
    for name in COHERENCE_METRICS:
        if name not in before:
            continue
        if name not in after or float(after[name]) < float(before[name]) - tol:
            degraded.append(name)
    return {"ok": not degraded, "degraded": degraded,
            "levels": {n: LEVEL_NAMES[COHERENCE_METRICS[n]] for n in degraded}}


def classify(
    kind: str,
    target: str,
    value: Any | None = None,
    paths: Any = None,
) -> str:
    """Return ``refused``, ``review`` or ``auto``.

    Touching L0 anywhere is refused. L1 is review only. Only an L2
    allowlisted param, in bounds, on a tuning kind, can be auto.
    Unknown targets default to review.
    """
    level = proposal_level(target, paths)
    if level == L0:
        return "refused"
    if level == L1:
        return "review"
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
    paths: Any = None,
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
    touched = [str(p) for p in (paths or []) if str(p).strip()]
    tier = classify(kind, target, value, touched)
    level = proposal_level(target, touched)
    return {
        "kind": kind,
        "target": target,
        "paths": touched,
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "tier": tier,
        "evidence": evidence,
        "verification_status": "verified" if candidate.get("verified") else "unverified",
        "proposal_status": "refused" if tier == "refused" else "pending",
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
            if item.get("tier") == "refused" or item.get("proposal_status") == "refused":
                return {"ok": False, "applied": False, "reason": "L0 changes are refused; they cannot be approved here",
                        "proposal": item}
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
        paths: Any = None,
        guard_before: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Record a proposal. Only L2 auto-tier items may apply on the store.

        L0 proposals are recorded as ``refused`` and never applied or
        approvable. L1 proposals stay pending review, whatever their
        target. Unverified candidates are recorded as pending review and
        are never auto-applied. Applying still does not touch Eat,
        learn, scars, or Titanos. ``guard_before`` holds the L0/L1
        coherence metrics on the held-out suite before the change; pass
        the after-metrics to ``OperationalStore.evaluate``.
        """
        proposal = proposal_from_candidate(
            candidate, kind=kind, target=target, value=value, paths=paths
        )
        if proposal["tier"] == "refused":
            proposal["reason"] = "touches the protected L0 substrate"
            return self.add(proposal)
        if proposal["level"] != L2:
            proposal["tier"] = "review"
            proposal["proposal_status"] = "pending"
            proposal["reason"] = "L1 changes go to review only"
            return self.add(proposal)
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
                guard_before=guard_before,
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
            if item.get("level_name"):
                lines.append(f"  - level: {item.get('level_name')}")
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
