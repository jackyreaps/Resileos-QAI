"""
Deterministic verifier swarm — staged checkers before durable learn.

Order (early reject wins):
  schema → sys_guard → relation_token → size → contradiction
  → provenance → temporal → capacity → hub_consistency

Each checker returns None (pass) or a reason string (fail).
No LLM. Auditable reason trail on EatDecision.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from resileos.kin.frames import classify_decision

# Optional frame / dimensionality tag (RES frame atlas — operational only)
FRAME_TAGS = frozenset(
    {
        "exact",          # structured store truth
        "reconstructed",  # derived / chain
        "abstained",
        "unresolved",
        "filtered",       # rejected by verifier
        "provisional",    # accepted with weak provenance
    }
)


@dataclass
class Claim:
    subject: str
    relation: str
    obj: str
    source: str = ""
    valid_until: str = ""  # ISO date optional
    hub: str = ""  # user: | world: | org: hint


@dataclass
class CheckResult:
    ok: bool
    reason: str = ""
    checker: str = ""


CheckerFn = Callable[[Claim, dict[str, Any]], CheckResult]


def _hub_of(subject: str) -> str:
    if subject.startswith("user:"):
        return "user"
    if subject.startswith("world:"):
        return "world"
    if subject.startswith("org:"):
        return "org"
    return "default"


def check_schema(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    if not claim.subject or not claim.relation or claim.obj is None or claim.obj == "":
        return CheckResult(False, "missing_subject_relation_or_obj", "schema")
    if len(claim.subject) > 200 or len(claim.relation) > 120:
        return CheckResult(False, "field_too_long", "schema")
    return CheckResult(True, "", "schema")


def check_sys_guard(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    if claim.subject.startswith("sys:") and not ctx.get("allow_sys"):
        return CheckResult(False, "sys_subject_forbidden", "sys_guard")
    return CheckResult(True, "", "sys_guard")


def check_relation_token(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    r = claim.relation
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", r):
        return CheckResult(False, "relation_not_token", "relation_token")
    return CheckResult(True, "", "relation_token")


def check_size(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    max_obj = int(ctx.get("max_obj_len", 500))
    if len(claim.obj) > max_obj:
        return CheckResult(False, "obj_too_long", "size")
    return CheckResult(True, "", "size")


def check_contradiction(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    """Reject if store has explicit not_<relation> or inverse conflict when provided."""
    ask = ctx.get("ask_fn")  # (s, r) -> value | list | None
    if not callable(ask):
        return CheckResult(True, "", "contradiction")
    neg = f"not_{claim.relation}"
    try:
        existing_neg = ask(claim.subject, neg)
    except Exception:
        existing_neg = None
    if existing_neg is not None and existing_neg != []:
        vals = existing_neg if isinstance(existing_neg, list) else [existing_neg]
        if claim.obj in [str(v) for v in vals] or str(existing_neg) == claim.obj:
            return CheckResult(False, "contradicts_not_relation", "contradiction")
    # same relation different locked value when ctx says single-valued
    if ctx.get("single_valued"):
        try:
            cur = ask(claim.subject, claim.relation)
        except Exception:
            cur = None
        if cur is not None and cur != [] and str(cur) != claim.obj:
            if not isinstance(cur, list) or (len(cur) == 1 and str(cur[0]) != claim.obj):
                if not isinstance(cur, list):
                    return CheckResult(
                        False, "contradicts_existing_value", "contradiction"
                    )
                if len(cur) == 1 and str(cur[0]) != claim.obj:
                    return CheckResult(
                        False, "contradicts_existing_value", "contradiction"
                    )
    return CheckResult(True, "", "contradiction")


def check_provenance(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    """If require_source, source must be non-empty and optionally allowlisted."""
    if not ctx.get("require_source"):
        return CheckResult(True, "", "provenance")
    if not (claim.source or "").strip():
        return CheckResult(False, "missing_source", "provenance")
    allow = ctx.get("source_allowlist")
    if allow is not None:
        if claim.source not in allow:
            return CheckResult(False, "source_not_allowlisted", "provenance")
    return CheckResult(True, "", "provenance")


def check_temporal(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    if not claim.valid_until:
        return CheckResult(True, "", "temporal")
    try:
        # date or datetime
        vu = claim.valid_until.replace("Z", "+00:00")
        if "T" in vu:
            dt = datetime.fromisoformat(vu)
        else:
            dt = datetime.fromisoformat(vu + "T23:59:59+00:00")
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < now:
            return CheckResult(False, "expired_valid_until", "temporal")
    except Exception:
        return CheckResult(False, "invalid_valid_until", "temporal")
    return CheckResult(True, "", "temporal")


def check_capacity(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    """Reject if hopfield_cap or facts_cap exceeded (caller supplies counts)."""
    cap = ctx.get("facts_cap")
    n = ctx.get("facts_count")
    if cap is not None and n is not None and int(n) >= int(cap):
        return CheckResult(False, "facts_cap_exceeded", "capacity")
    hop = ctx.get("hopfield_cap")
    hop_n = ctx.get("hopfield_count")
    if hop is not None and hop_n is not None and int(hop_n) >= int(hop):
        return CheckResult(False, "hopfield_cap_exceeded", "capacity")
    return CheckResult(True, "", "capacity")


def check_hub_consistency(claim: Claim, ctx: dict[str, Any]) -> CheckResult:
    """
    org: policy subjects should not be overwritten from user hub claims
    when ctx locks org policy.
    """
    locked = ctx.get("locked_hubs") or set()
    hub = _hub_of(claim.subject)
    if hub in locked and not ctx.get("allow_locked_write"):
        return CheckResult(False, f"hub_locked:{hub}", "hub_consistency")
    return CheckResult(True, "", "hub_consistency")


DEFAULT_PIPELINE: list[CheckerFn] = [
    check_schema,
    check_sys_guard,
    check_relation_token,
    check_size,
    check_contradiction,
    check_provenance,
    check_temporal,
    check_capacity,
    check_hub_consistency,
]


@dataclass
class VerifierReport:
    action: str  # accept | reject | abstain
    claim: Optional[Claim] = None
    reason: str = ""
    trail: list[dict[str, str]] = field(default_factory=list)
    frame: str = "filtered"
    dim: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "subject": self.claim.subject if self.claim else "",
            "relation": self.claim.relation if self.claim else "",
            "obj": self.claim.obj if self.claim else "",
            "reason": self.reason,
            "trail": list(self.trail),
            "frame": self.frame,
            "dim": self.dim,
            "source": self.claim.source if self.claim else "",
        }


def parse_claim(raw: str | dict[str, Any]) -> Optional[Claim]:
    if isinstance(raw, dict):
        s = str(raw.get("subject") or "").strip()
        r = str(raw.get("relation") or "").strip()
        o = raw.get("obj", raw.get("object", ""))
        o = str(o).strip() if o is not None else ""
        if not s or not r or not o:
            return None
        return Claim(
            subject=s,
            relation=r,
            obj=o,
            source=str(raw.get("source") or ""),
            valid_until=str(raw.get("valid_until") or ""),
            hub=str(raw.get("hub") or ""),
        )
    text = (raw or "").strip()
    if not text:
        return None
    low = text.lower()
    if low.endswith("?") or low.startswith(
        ("what ", "who ", "why ", "how ", "when ", "where ", "is ", "are ")
    ):
        return None
    parts = text.split()
    if len(parts) < 3:
        return None
    return Claim(subject=parts[0], relation=parts[1], obj=" ".join(parts[2:]))


def run_verifiers(
    raw: str | dict[str, Any],
    *,
    ctx: Optional[dict[str, Any]] = None,
    pipeline: Optional[list[CheckerFn]] = None,
) -> VerifierReport:
    """
    Full swarm pass. Unparseable prose → abstain (frame unresolved/abstained).
    """
    ctx = dict(ctx or {})
    claim = parse_claim(raw)
    if claim is None:
        return VerifierReport(
            action="abstain",
            reason="unstructured_prose",
            trail=[{"checker": "parse", "reason": "unstructured_prose"}],
            frame="abstained",
            dim="",
        )
    trail: list[dict[str, str]] = []
    for fn in pipeline or DEFAULT_PIPELINE:
        res = fn(claim, ctx)
        trail.append({"checker": res.checker, "reason": res.reason or "ok"})
        if not res.ok:
            c = classify_decision("reject", subject=claim.subject)
            return VerifierReport(
                action="reject",
                claim=claim,
                reason=res.reason,
                trail=trail,
                frame=c["frame"],
                dim=c["dim"],
            )
    c = classify_decision(
        "accept",
        subject=claim.subject,
        has_source=bool(claim.source),
    )
    return VerifierReport(
        action="accept",
        claim=claim,
        reason="ok",
        trail=trail,
        frame=c["frame"],
        dim=c.get("dim", ""),
    )
