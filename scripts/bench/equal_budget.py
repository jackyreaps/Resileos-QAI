#!/usr/bin/env python3
"""Equal-budget comparison: Kin + Demi-gods + Hades vs one residual/Apollo call.

Both paths see the same fact table and the same step budget. The residual
path is one lookup plus ``apollo_success``. The hierarchy path spends
steps on a Kin cycle, Hephaestus, Atlas, Momus, and a Hades checkpoint.
Scoring uses the fixture's expected object. Neither path is given that
expected value.

Fact rows come from ``configs/titanos-facts.json``. Temporal rows use the
windows in ``scripts/run_temporal_probe.py`` (obj_A 1800–1900, obj_B from
1850). Overlap and dates outside every window must abstain.

Usage:
    PYTHONPATH=src:scripts python scripts/bench/equal_budget.py \
        --out landing/artifacts/report_equal_budget_YYYY-MM-DD.json
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FACTS = ROOT / "configs" / "titanos-facts.json"
DEFAULT_BUDGET = 8

# Same windows as scripts/run_temporal_probe.py::_synthetic_overlap_m9.
TEMPORAL_ROWS = (
    ("test:temporal_subject", "capital_of", "obj_A", "1800-01-01", "1900-01-01"),
    ("test:temporal_subject", "capital_of", "obj_B", "1850-01-01", None),
)
TEMPORAL_TASKS = (
    ("test:temporal_subject", "capital_of", "1820-01-01", "obj_A"),
    ("test:temporal_subject", "capital_of", "1860-01-01", None),
    ("test:temporal_subject", "capital_of", "1950-01-01", "obj_B"),
    ("test:temporal_subject", "capital_of", "1750-01-01", None),
)


def _covers(
    valid_from: str | None,
    valid_to: str | None,
    as_of: str | None,
) -> bool:
    """ISO dates compare in order. ``valid_to`` is the first day outside the window."""
    if as_of is None:
        return True
    if valid_from and as_of < valid_from:
        return False
    if valid_to and as_of >= valid_to:
        return False
    return True


def load_store(facts_path: Path | str = DEFAULT_FACTS) -> list[tuple]:
    raw = json.loads(Path(facts_path).read_text(encoding="utf-8"))
    rows = []
    for fact in raw["facts"]:
        subject, relation, obj = fact[0], fact[1], fact[2]
        valid_from = fact[3] if len(fact) > 3 else None
        valid_to = fact[4] if len(fact) > 4 else None
        rows.append((subject, relation, obj, valid_from, valid_to))
    rows.extend(TEMPORAL_ROWS)
    return rows


def lookup(
    rows: list[tuple],
    subject: str,
    relation: str,
    as_of: str | None,
) -> list[str]:
    found = []
    for s, r, obj, valid_from, valid_to in rows:
        if s == subject and r == relation and _covers(valid_from, valid_to, as_of):
            found.append(obj)
    return found


def build_tasks(rows: list[tuple]) -> list[dict[str, Any]]:
    """Known single-valued domain facts, absent pairs, and the temporal probe."""
    tasks = []
    seen = set()
    for subject, relation, obj, _vf, _vt in rows:
        if relation != "domain":
            continue
        key = (subject, relation, None)
        if key in seen:
            continue
        seen.add(key)
        tasks.append(
            {
                "subject": subject,
                "relation": relation,
                "as_of": None,
                "expect": obj,
                "kind": "known",
            }
        )
    for subject, relation in (
        ("Nobody", "domain"),
        ("Zeus", "not_a_relation"),
        ("sky", "parent_of"),
        ("forge", "is_a"),
    ):
        tasks.append(
            {
                "subject": subject,
                "relation": relation,
                "as_of": None,
                "expect": None,
                "kind": "unknown",
            }
        )
    for subject, relation, as_of, expect in TEMPORAL_TASKS:
        tasks.append(
            {
                "subject": subject,
                "relation": relation,
                "as_of": as_of,
                "expect": expect,
                "kind": "temporal",
            }
        )
    return tasks


def _hash_for(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _score(task: dict, obj: Any) -> dict[str, bool]:
    expect = task["expect"]
    abstained = obj is None
    if expect is None:
        correct = abstained
        false_accept = obj is not None
    else:
        correct = obj == expect
        false_accept = obj is not None and obj != expect
    return {
        "correct": correct,
        "abstained": abstained,
        "should_abstain": expect is None,
        "false_accept": false_accept,
    }


def residual_call(task: dict, rows: list[tuple], budget_steps: int) -> dict[str, Any]:
    """One lookup and one apollo_success. Costs one step when the budget allows."""
    from resileos.harness.tools import apollo_success

    if budget_steps < 1:
        return {"obj": None, "steps": 0, "apollo": None}
    found = lookup(rows, task["subject"], task["relation"], task["as_of"])
    if len(found) == 1:
        apollo = apollo_success({"status": "ok"})
        obj = found[0] if apollo.get("success") else None
    else:
        apollo = apollo_success({"status": "abstain"})
        obj = None
    return {"obj": obj, "steps": 1, "apollo": apollo}


def hierarchy_call(
    task: dict,
    rows: list[tuple],
    budget_steps: int,
    hades_dir: Path,
) -> dict[str, Any]:
    """Kin cycle, Hephaestus, Atlas, Momus, then Hades. Stop at the step budget."""
    from resileos.harness.packet import ControlPacket
    from resileos.kin.bundle import build_kin_bundle
    from resileos.kin.demigods import atlas_check, hephaestus_check, momus_review
    from resileos.kin.hades import Hades

    steps = 0

    def take() -> bool:
        nonlocal steps
        if steps >= budget_steps:
            return False
        steps += 1
        return True

    if not take():
        return {"obj": None, "steps": steps, "stopped": "budget"}

    found = lookup(rows, task["subject"], task["relation"], task["as_of"])
    if len(found) == 1:
        artefact = {"status": "ok", "obj": found[0]}
    else:
        artefact = {"status": "abstain", "obj": None}

    packet = ControlPacket(id="equal-budget")
    packet.budget_remaining = {
        "steps": float(budget_steps),
        "cost": 1.0,
        "tokens": 1000.0,
    }
    packet.evidence = [
        {"source": "probe", "result": {"matched": len(found), "passed": len(found)}}
    ]
    packet.state["n_facts"] = len(rows)
    packet.verified = True

    if not take():
        return {"obj": None, "steps": steps, "stopped": "budget"}
    bundle = build_kin_bundle()
    bundle._hades = Hades(store_dir=hades_dir)
    _cycle_report, _policy, harness = bundle.cycle(
        metrics={
            "hits": 1 if len(found) == 1 else 0,
            "misses": 0 if len(found) == 1 else 1,
        }
    )
    consistency = harness.get("consistency") if isinstance(harness, dict) else None
    cycle_meta = {
        "cycle_verified": (
            bool(harness.get("verified")) if isinstance(harness, dict) else False
        ),
        "cycle_consistent": (
            bool(consistency.get("consistent"))
            if isinstance(consistency, dict)
            else False
        ),
        "cycle_reason": (
            str(harness.get("reason") or "") if isinstance(harness, dict) else ""
        ),
    }

    if not take():
        return {"obj": None, "steps": steps, "stopped": "budget", **cycle_meta}
    joints = hephaestus_check(packet)

    if not take():
        return {"obj": None, "steps": steps, "stopped": "budget", **cycle_meta}
    capacity = atlas_check(packet, n_facts=len(rows))

    digest = _hash_for(
        {"status": artefact["status"], "obj": artefact["obj"]}
    )
    spec = {
        "requirements": [
            {"location": "status", "equals": artefact["status"]},
        ]
    }
    if not take():
        return {"obj": None, "steps": steps, "stopped": "budget", **cycle_meta}
    review = momus_review(artefact, spec, digest)

    passed = bool(joints.verified and capacity.verified and review.verified)
    if not passed:
        return {
            "obj": None,
            "steps": steps,
            "stopped": "check",
            "hephaestus": joints.verified,
            "atlas": capacity.verified,
            "momus": review.outcome,
            **cycle_meta,
        }

    if not take():
        return {"obj": None, "steps": steps, "stopped": "budget", **cycle_meta}
    lesson = (
        f"equal-budget turn={packet.turn} verified=True "
        f"status={artefact['status']}"
    )
    bundle._hades.save(packet, residual_packet_hash=digest, lesson=lesson)
    return {
        "obj": artefact["obj"],
        "steps": steps,
        "stopped": "answered",
        **cycle_meta,
    }


def _summarize(task_rows: list[dict]) -> dict[str, Any]:
    n = len(task_rows)
    correct = sum(1 for row in task_rows if row["correct"])
    should = [row for row in task_rows if row["should_abstain"]]
    correct_abstain = sum(1 for row in should if row["abstained"] and row["correct"])
    false_accepts = sum(1 for row in task_rows if row["false_accept"])
    steps = [row["steps"] for row in task_rows]
    latency = [row["latency_ms"] for row in task_rows]
    out = {
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "correct": correct,
        "correct_abstain_rate": (
            correct_abstain / len(should) if should else 0.0
        ),
        "should_abstain": len(should),
        "false_accepts": false_accepts,
        "false_accept_rate": false_accepts / n if n else 0.0,
        "latency_ms_total": sum(latency),
        "latency_ms_mean": sum(latency) / n if n else 0.0,
        "steps_total": sum(steps),
        "steps_mean": sum(steps) / n if n else 0.0,
        "steps_max": max(steps) if steps else 0,
    }
    if any("cycle_verified" in row for row in task_rows):
        out["cycle_verified"] = sum(
            1 for row in task_rows if row.get("cycle_verified") is True
        )
        out["cycle_consistent"] = sum(
            1 for row in task_rows if row.get("cycle_consistent") is True
        )
        out["cycle_observed"] = sum(
            1 for row in task_rows if "cycle_verified" in row
        )
        reasons: dict[str, int] = {}
        for row in task_rows:
            reason = str(row.get("cycle_reason") or "")
            if not reason:
                continue
            reasons[reason] = reasons.get(reason, 0) + 1
        out["cycle_reasons"] = reasons
    return out


def run_equal_budget(
    facts_path: Path | str = DEFAULT_FACTS,
    budget_steps: int = DEFAULT_BUDGET,
    hades_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Run both paths. ``hades_dir`` receives hierarchy checkpoints."""
    import tempfile

    rows = load_store(facts_path)
    tasks = build_tasks(rows)
    own_dir = None
    if hades_dir is None:
        own_dir = tempfile.TemporaryDirectory()
        hades_path = Path(own_dir.name)
    else:
        hades_path = Path(hades_dir)
        hades_path.mkdir(parents=True, exist_ok=True)

    def _run(path_name: str, call) -> list[dict]:
        out = []
        for index, task in enumerate(tasks):
            started = time.perf_counter()
            if path_name == "hierarchy":
                result = call(task, rows, budget_steps, hades_path / f"t{index}")
            else:
                result = call(task, rows, budget_steps)
            elapsed = (time.perf_counter() - started) * 1000.0
            scored = _score(task, result["obj"])
            out.append(
                {
                    "kind": task["kind"],
                    "subject": task["subject"],
                    "relation": task["relation"],
                    "as_of": task["as_of"],
                    "obj": result["obj"],
                    "steps": result["steps"],
                    "latency_ms": elapsed,
                    **scored,
                    **(
                        {
                            "cycle_verified": result["cycle_verified"],
                            "cycle_consistent": result["cycle_consistent"],
                            "cycle_reason": result.get("cycle_reason", ""),
                        }
                        if "cycle_verified" in result
                        else {}
                    ),
                }
            )
        return out

    try:
        residual_rows = _run("residual", residual_call)
        hierarchy_rows = _run("hierarchy", hierarchy_call)
    finally:
        if own_dir is not None:
            own_dir.cleanup()

    residual = _summarize(residual_rows)
    hierarchy = _summarize(hierarchy_rows)
    return {
        "budget_steps": budget_steps,
        "facts": str(facts_path),
        "temporal_source": "scripts/run_temporal_probe.py synthetic windows",
        "n_tasks": len(tasks),
        "residual": residual,
        "hierarchy": hierarchy,
        "accuracy_delta": hierarchy["accuracy"] - residual["accuracy"],
        "false_accept_delta": (
            hierarchy["false_accepts"] - residual["false_accepts"]
        ),
        "note": (
            "The hierarchy path answers from the same lookup as the "
            "residual path. Momus checks that lookup's own status. Extra "
            "checks can only abstain; they cannot add a fact the store "
            "does not hold."
        ),
    }


def main() -> None:
    import argparse
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    from bench.measure_meta import dated_artifact, environment, utc_now

    parser = argparse.ArgumentParser(description="Equal-budget measurement")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = run_equal_budget()
    report["measured_at"] = utc_now()
    report["environment"] = environment()
    text = json.dumps(report, indent=2) + "\n"
    print(text, end="")
    out = args.out or dated_artifact("equal_budget")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
