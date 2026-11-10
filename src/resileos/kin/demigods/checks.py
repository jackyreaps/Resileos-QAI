"""Deterministic Demi-god duties.

The guides are persona text. These functions are the duties. They call
the harness primitives that already exist and return a DemigodResult.
Nothing here calls a model.
"""
from __future__ import annotations

import json
import re
from typing import Any

from resileos.capacity import hopfield_cap
from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    EVIDENCE_CAP,
    apollo_success,
    budget_and_stuck_guard,
    residual_consistency,
)
from resileos.kin.hermes import HermesBudget
from resileos.kin.verifiers import Claim, check_capacity

from .hierarchy import (
    DemigodHierarchyError,
    demigod_duty,
    residual_hash_only,
)
from .results import Defect, finish

_VERIFIED_TRUE = re.compile(r"verified\s*=\s*true\b", re.IGNORECASE)
_VERIFIED_FALSE = re.compile(r"verified\s*=\s*false\b", re.IGNORECASE)
_CRITERION_LINE = re.compile(
    r"^(?:[-*]\s*)?(?:criterion|success|must)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_SPEC_LINE = re.compile(
    r"^(?:[-*]\s*)?(?:MUST|REQUIRED|must|criterion|success)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_HASH = re.compile(r"^[0-9a-f]{64}$")

# Stripped before Momus compares. Values are never read.
_BLIND_KEYS = frozenset(
    {
        "history",
        "control_history",
        "author_notes",
        "author_note",
        "evidence_gist",
        "reasoning",
    }
)
_FORBIDDEN_KW = {
    "learn": "a demigod cannot call learn",
    "learn_fn": "a demigod cannot call learn",
    "learn_batch": "a demigod cannot call learn",
    "residual_core": "a demigod cannot own the residual core",
    "residual_packet": "a demigod cannot own the residual core",
    "demigod_summon": "a demigod cannot summon another demigod",
}


def _as_dict(packet: Any) -> dict[str, Any]:
    if isinstance(packet, ControlPacket):
        return packet.to_dict()
    if isinstance(packet, dict):
        return packet
    raise TypeError("packet must be a ControlPacket or a dict")


def _lesson_text(lesson: Any) -> str:
    if lesson is None:
        return ""
    if isinstance(lesson, str):
        return lesson
    if hasattr(lesson, "lesson") and isinstance(lesson.lesson, str):
        return lesson.lesson
    return ""


def _lesson_signal(lesson: Any) -> str:
    """Return 'true', 'false', 'conflict', or 'missing'."""
    text = _lesson_text(lesson)
    if not text.strip():
        return "missing"
    affirms = _VERIFIED_TRUE.search(text) is not None
    denies = _VERIFIED_FALSE.search(text) is not None
    if affirms and denies:
        return "conflict"
    if affirms:
        return "true"
    if denies:
        return "false"
    return "missing"


def _real_evidence(packet: dict[str, Any]) -> list[dict]:
    out = []
    for item in packet.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        if item.get("source") in (None, "", "summary", "note"):
            continue
        out.append(item)
    return out


def themis_check(
    packet: Any,
    apollo_result: Any,
    lesson: Any,
    *,
    artefact: Any = None,
    residual_packet: Any = None,
) -> Any:
    """Verified only when residual consistency, Apollo, and the lesson agree.

    A missing packet, Apollo status, lesson signal, or evidence entry fails.
    Themis calls ``residual_consistency`` and ``apollo_success``. It does
    not invent either result. ``artefact`` is accepted and not scored;
    certification does not re-enter the author's reasoning.
    """
    del artefact  # persona rule: do not re-enter the author's reasoning
    with demigod_duty("themis"):
        missing: list[str] = []
        pkt: dict[str, Any] | None
        if packet is None:
            missing.append("packet")
            pkt = None
        else:
            pkt = _as_dict(packet)
        apollo = None
        if not isinstance(apollo_result, dict) or "status" not in apollo_result:
            missing.append("apollo_result")
        else:
            apollo = apollo_success(apollo_result)
        signal = _lesson_signal(lesson)
        if signal == "missing":
            missing.append("lesson")
        consistency = None
        if pkt is not None:
            if not _real_evidence(pkt):
                missing.append("evidence")
            consistency = residual_consistency(pkt)
        digest = residual_hash_only(residual_packet)
        evidence: list[dict] = []
        if consistency is not None:
            evidence.append({"source": "residual_consistency", "result": consistency})
        if apollo is not None:
            evidence.append({"source": "apollo_success", "result": apollo})
        evidence.append(
            {
                "source": "hades_lesson",
                "result": {
                    "signal": signal,
                    "lesson": _lesson_text(lesson) or None,
                },
            }
        )
        if digest is not None:
            evidence.append(
                {"source": "residual_packet_hash", "result": {"packet_hash": digest}}
            )
        if missing:
            return finish(
                "themis",
                False,
                "missing evidence: " + ", ".join(missing),
                evidence,
            )
        if signal == "conflict":
            return finish(
                "themis",
                False,
                "lesson conflicts with itself on verified",
                evidence,
            )
        assert consistency is not None and apollo is not None
        residual_ok = bool(consistency.get("consistent"))
        apollo_ok = bool(apollo.get("success"))
        lesson_ok = signal == "true"
        if digest is not None and pkt is not None:
            for item in pkt.get("evidence") or []:
                if not isinstance(item, dict) or item.get("source") != "residual_core":
                    continue
                recorded = (item.get("result") or {}).get("packet_hash")
                if recorded and recorded != digest:
                    return finish(
                        "themis",
                        False,
                        "residual hash disagrees with residual_core evidence",
                        evidence,
                    )
        if residual_ok and apollo_ok and lesson_ok:
            return finish(
                "themis",
                True,
                "residual consistency, apollo success, and the hades lesson agree",
                evidence,
            )
        parts: list[str] = []
        if not residual_ok:
            parts.append(str(consistency.get("reason") or "residual inconsistency"))
        if not apollo_ok:
            parts.append(str(apollo.get("reason") or "apollo did not report success"))
        if not lesson_ok:
            parts.append("lesson does not affirm verified=true")
        return finish("themis", False, "; ".join(parts), evidence)


def _strip_blind(value: Any, stripped: list[str], path: str = "") -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            here = f"{path}{key}" if not path else f"{path}.{key}"
            if key in _BLIND_KEYS:
                stripped.append(here)
                continue
            out[key] = _strip_blind(item, stripped, here)
        return out
    if isinstance(value, list):
        return [
            _strip_blind(item, stripped, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


def _lookup(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _contains(artefact: Any, needle: str) -> bool:
    if isinstance(artefact, str):
        return needle in artefact
    try:
        blob = json.dumps(artefact, sort_keys=True, default=str)
    except TypeError:
        blob = str(artefact)
    return needle in blob


def _severity(value: Any) -> str:
    if value in {"error", "warning"}:
        return str(value)
    return "error"


def _requirements_from_spec(spec: Any) -> list[dict[str, Any]]:
    if isinstance(spec, dict):
        raw = spec.get("requirements")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        return []
    if isinstance(spec, list):
        return [item for item in spec if isinstance(item, dict)]
    if isinstance(spec, str):
        found: list[dict[str, Any]] = []
        for index, line in enumerate(spec.splitlines(), start=1):
            match = _SPEC_LINE.match(line.strip())
            if match is None:
                continue
            body = match.group(1).strip()
            if body.lower().startswith("contains:"):
                found.append(
                    {
                        "location": f"spec:{index}",
                        "contains": body.split(":", 1)[1],
                        "severity": "error",
                    }
                )
            elif "=" in body:
                path, expected = body.split("=", 1)
                found.append(
                    {
                        "location": path.strip(),
                        "equals": expected.strip(),
                        "severity": "error",
                    }
                )
            else:
                found.append(
                    {
                        "location": f"spec:{index}",
                        "contains": body,
                        "severity": "error",
                    }
                )
        return found
    return []


def _requirement_defect(artefact: Any, req: dict[str, Any]) -> Defect | None:
    location = str(req.get("location") or "artefact")
    severity = _severity(req.get("severity"))
    if "equals" in req:
        actual = _lookup(artefact, location)
        expected = req.get("equals")
        if str(actual) != str(expected):
            return Defect(
                location,
                severity,
                f"expected {expected!r}, found {actual!r}",
            )
        return None
    if "contains" in req:
        needle = str(req.get("contains"))
        if not _contains(artefact, needle):
            return Defect(location, severity, f"missing {needle!r}")
        return None
    if req.get("present") is True:
        if _lookup(artefact, location) is None:
            return Defect(location, severity, "required value is absent")
        return None
    return Defect(location, "error", "requirement has no equals, contains, or present check")


def _hash_defects(residual_hash: Any, *, have_requirements: bool) -> tuple[list[Defect], int]:
    if residual_hash is None:
        if not have_requirements:
            return [], 0
        return [
            Defect("residual_hash", "error", "missing residual hash")
        ], 1
    if isinstance(residual_hash, str) and _HASH.fullmatch(residual_hash):
        return [], 1
    return [
        Defect(
            "residual_hash",
            "error",
            "residual hash is not 64 lowercase hex characters",
        )
    ], 1


def momus_review(
    artefact: Any,
    spec: Any,
    residual_hash: str | None = None,
    **blind: Any,
) -> Any:
    """Blind reviewer. Sees the artefact, the spec, and the residual hash.

    Control history and author notes are stripped and never consulted.
    Extra callables such as learn are refused. With no requirement checks
    to run, Momus cannot approve.
    """
    for key, message in _FORBIDDEN_KW.items():
        if key in blind:
            raise DemigodHierarchyError(message)
    with demigod_duty("momus"):
        stripped: list[str] = []
        for key in blind:
            stripped.append(key)
        # Do not read blind values. Discard them.
        seen = _strip_blind(artefact, stripped)
        spec_view = _strip_blind(spec, stripped)
        requirements = _requirements_from_spec(spec_view)
        defects: list[Defect] = []
        for req in requirements:
            found = _requirement_defect(seen, req)
            if found is not None:
                defects.append(found)
        hash_defects, hash_checks = _hash_defects(
            residual_hash, have_requirements=bool(requirements)
        )
        defects.extend(hash_defects)
        requirement_checks = len(requirements)
        checks_run = requirement_checks + hash_checks
        if requirement_checks == 0 and checks_run == 0:
            ok = False
            reason = "no checks to run"
        elif requirement_checks == 0:
            ok = False
            reason = "no requirement checks to run"
        elif defects:
            ok = False
            reason = f"{len(defects)} defect(s)"
        else:
            ok = False if defects else True
            reason = f"{requirement_checks} requirement(s) hold"
        # Approval is impossible when nothing was checked or a defect remains.
        if requirement_checks == 0 or defects:
            ok = False
        evidence = [
            {
                "source": "momus",
                "checks_run": checks_run,
                "requirement_checks": requirement_checks,
                "stripped": sorted(set(stripped)),
                "defects": [item.to_dict() for item in defects],
            }
        ]
        return finish("momus", ok, reason, evidence, defects)


def _hermes_limits(budget: Any) -> tuple[bool, dict[str, Any]]:
    if budget is None:
        return False, {"checked": False}
    if isinstance(budget, HermesBudget):
        used, max_items, max_depth = budget.used, budget.max_items, budget.max_depth
    elif isinstance(budget, dict):
        try:
            used = int(budget.get("used", 0))
            max_items = int(budget.get("max_items", 0))
            max_depth = int(budget.get("max_depth", 0))
        except (TypeError, ValueError):
            return True, {"checked": True, "reason": "unreadable hermes budget"}
    else:
        return True, {"checked": True, "reason": "unreadable hermes budget"}
    over = used > max_items or max_items < 0 or max_depth < 0
    return over, {
        "checked": True,
        "used": used,
        "max_items": max_items,
        "max_depth": max_depth,
        "over": over,
    }


def hephaestus_check(
    packet: Any,
    *,
    hermes_budget: Any = None,
    n_facts: int | None = None,
    hopfield_count: int | None = None,
    residual_packet: Any = None,
) -> Any:
    """Pass only when consistency, scars, budget, and capacity all hold.

    Uses ``residual_consistency``, ``budget_and_stuck_guard``,
    ``check_capacity``, and ``hopfield_cap``. A declared fact load is
    compared with ``hopfield_cap``. Evidence length uses ``EVIDENCE_CAP``.
    """
    with demigod_duty("hephaestus"):
        if packet is None:
            return finish("hephaestus", False, "missing control packet", [])
        pkt = _as_dict(packet)
        digest = residual_hash_only(residual_packet)
        failures: list[str] = []
        evidence: list[dict] = []

        consistency = residual_consistency(pkt)
        evidence.append({"check": "residual_consistency", "result": consistency})
        if not consistency.get("consistent"):
            failures.append(str(consistency.get("reason") or "residual inconsistency"))

        scars = list(pkt.get("scars") or [])
        evidence.append({"check": "scars", "count": len(scars), "scars": scars})
        if scars and not any("scar" in item for item in failures):
            failures.append(f"{len(scars)} unresolved scars")

        budget = pkt.get("budget_remaining")
        if not isinstance(budget, dict) or "steps" not in budget or "cost" not in budget:
            failures.append("missing budget")
            evidence.append({"check": "budget", "ok": False, "reason": "missing budget"})
        else:
            probe = {
                "budget_remaining": dict(budget),
                "history": list(pkt.get("history") or []),
                "last_hash": pkt.get("last_hash"),
            }
            guard = budget_and_stuck_guard(probe)
            evidence.append({"check": "budget", "result": guard})
            if not guard.get("ok"):
                failures.append(str(guard.get("reason") or "budget exhausted"))

        state = pkt.get("state") if isinstance(pkt.get("state"), dict) else {}
        facts_count = n_facts
        if facts_count is None and "n_facts" in state:
            facts_count = state.get("n_facts")
        hop_count = hopfield_count
        if hop_count is None and "hopfield_count" in state:
            hop_count = state.get("hopfield_count")
        cap = hopfield_cap()
        ctx: dict[str, Any] = {}
        if facts_count is not None:
            ctx["facts_cap"] = cap
            ctx["facts_count"] = int(facts_count)
        if hop_count is not None:
            ctx["hopfield_cap"] = cap
            ctx["hopfield_count"] = int(hop_count)
        claim = Claim(subject="demigod:hephaestus", relation="checks", obj="packet")
        cap_result = check_capacity(claim, ctx)
        evidence_len = len(pkt.get("evidence") or [])
        over_evidence = evidence_len > EVIDENCE_CAP
        evidence.append(
            {
                "check": "capacity",
                "hopfield_cap": cap,
                "facts_count": facts_count,
                "hopfield_count": hop_count,
                "ok": cap_result.ok and not over_evidence,
                "reason": cap_result.reason,
                "checker": cap_result.checker,
                "evidence_len": evidence_len,
                "evidence_cap": EVIDENCE_CAP,
            }
        )
        if not cap_result.ok:
            failures.append(cap_result.reason or "capacity exceeded")
        if over_evidence:
            failures.append(
                f"evidence length {evidence_len} exceeds cap {EVIDENCE_CAP}"
            )

        over_hermes, hermes_ev = _hermes_limits(hermes_budget)
        evidence.append({"check": "hermes_budget", **hermes_ev})
        if over_hermes:
            failures.append("hermes budget exceeded")

        if digest is not None:
            evidence.append(
                {"check": "residual_packet_hash", "packet_hash": digest}
            )

        if failures:
            return finish("hephaestus", False, "; ".join(failures), evidence)
        return finish(
            "hephaestus",
            True,
            "residual consistent, no scars, budget holds, within capacity",
            evidence,
        )


def _parse_criteria(source: Any) -> list[str]:
    if source is None:
        return []
    if hasattr(source, "lesson") and not isinstance(source, (str, dict, list)):
        return _parse_criteria(source.lesson)
    if isinstance(source, dict):
        raw = source.get("criteria")
        if raw is None:
            raw = source.get("success_criteria")
        if isinstance(raw, str):
            return _parse_criteria(raw)
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return []
    if isinstance(source, list):
        return [str(item).strip() for item in source if str(item).strip()]
    if isinstance(source, str):
        found = []
        for line in source.splitlines():
            match = _CRITERION_LINE.match(line.strip())
            if match is not None and match.group(1).strip():
                found.append(match.group(1).strip())
        return found
    return []


def _collect_criteria(*sources: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in _parse_criteria(source):
            if item not in seen:
                seen.add(item)
                found.append(item)
    return found


def _eval_criterion(
    criterion: str,
    artefact: Any,
    apollo: dict[str, Any] | None,
    consistency: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    backed = bool(apollo and apollo.get("success")) or bool(
        consistency and consistency.get("consistent")
    )
    if criterion == "apollo:success":
        ok = bool(apollo and apollo.get("success"))
        return ok, {"criterion": criterion, "ok": ok, "channel": "apollo"}
    if criterion == "residual:consistent":
        ok = bool(consistency and consistency.get("consistent"))
        return ok, {"criterion": criterion, "ok": ok, "channel": "residual"}
    if criterion.startswith("contains:"):
        needle = criterion.split(":", 1)[1]
        ok = backed and _contains(artefact, needle)
        return ok, {"criterion": criterion, "ok": ok, "channel": "residual_or_apollo"}
    if criterion.startswith("field:"):
        body = criterion.split(":", 1)[1]
        path, sep, expected = body.partition("=")
        if sep == "":
            ok = False
        else:
            actual = _lookup(artefact, path.strip())
            ok = backed and str(actual) == expected.strip()
        return ok, {"criterion": criterion, "ok": ok, "channel": "residual_or_apollo"}
    return False, {
        "criterion": criterion,
        "ok": False,
        "channel": "none",
        "reason": "unknown criterion form",
    }


def nike_check(
    lesson: Any = None,
    task_brief: Any = None,
    *,
    artefact: Any = None,
    apollo_result: Any = None,
    packet: Any = None,
) -> Any:
    """Binary success against explicit criteria. No criteria means fail.

    Criteria come from ``criterion:``, ``success:``, or ``must:`` lines,
    or from a ``criteria`` / ``success_criteria`` list. ``field:`` and
    ``contains:`` count only when Apollo succeeded or the residual packet
    is consistent. There is no partial credit.
    """
    with demigod_duty("nike"):
        criteria = _collect_criteria(lesson, task_brief)
        if not criteria:
            return finish("nike", False, "no explicit success criteria", [])
        if apollo_result is None and packet is None:
            return finish(
                "nike",
                False,
                "missing residual or apollo evidence",
                [{"criteria": criteria}],
            )
        apollo = None
        if isinstance(apollo_result, dict) and "status" in apollo_result:
            apollo = apollo_success(apollo_result)
        consistency = None
        if packet is not None:
            consistency = residual_consistency(_as_dict(packet))
        rows = []
        failed: list[str] = []
        for criterion in criteria:
            ok, row = _eval_criterion(criterion, artefact, apollo, consistency)
            rows.append(row)
            if not ok:
                failed.append(criterion)
        evidence: list[dict] = [{"check": "criteria", "results": rows}]
        if apollo is not None:
            evidence.append({"source": "apollo_success", "result": apollo})
        if consistency is not None:
            evidence.append({"source": "residual_consistency", "result": consistency})
        if failed:
            return finish(
                "nike",
                False,
                "criteria failed: " + "; ".join(failed),
                evidence,
            )
        return finish("nike", True, f"{len(criteria)} criteria hold", evidence)
