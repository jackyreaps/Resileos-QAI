#!/usr/bin/env python3
"""Run the dated measurement legs and write an index artifact.

Does not start an API server. Does not call an LLM unless both
BENCH_LLM_URL and BENCH_LLM_KEY are already set (the memory bench
reads them itself). Does not generate the 5k-fact corpus.

Usage (from the repo root):
    PYTHONPATH=src:scripts python scripts/ops/publish_measurements.py
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from bench.measure_meta import dated_artifact, environment, redact_text, utc_day, utc_now


def _python() -> str:
    return sys.executable or "python3"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "scripts"), env.get("PYTHONPATH", "")]
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(args: list[str]) -> dict:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
    )
    stdout = redact_text(proc.stdout or "")
    stderr = redact_text(proc.stderr or "")
    tail = (stderr or stdout)[-1500:]
    return {
        "exit_code": proc.returncode,
        "stderr_tail": tail if proc.returncode else "",
    }


def _http_listening(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if not host:
            return False
        port = parts.port or (443 if parts.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> int:
    day = utc_day()
    paths = {
        "memory_vs_llm": dated_artifact("memory_vs_llm", day),
        "equal_budget": dated_artifact("equal_budget", day),
        "temporal_probe": dated_artifact("temporal_probe", day),
        "compositional": dated_artifact("compositional", day),
        "latency_m5": dated_artifact("latency_m5", day),
        "mouth_leak": dated_artifact("mouth_leak", day),
    }
    py = _python()
    commands = {
        "memory_vs_llm": [
            py,
            str(ROOT / "scripts" / "ops" / "bench_vs_llm.py"),
            "--out",
            str(paths["memory_vs_llm"]),
        ],
        "equal_budget": [
            py,
            str(ROOT / "scripts" / "bench" / "equal_budget.py"),
            "--out",
            str(paths["equal_budget"]),
        ],
        "temporal_probe": [
            py,
            str(ROOT / "scripts" / "run_temporal_probe.py"),
            "--facts",
            str(ROOT / "configs" / "titanos-facts.json"),
            "--out",
            str(paths["temporal_probe"]),
        ],
        "compositional": [
            py,
            str(ROOT / "scripts" / "ops" / "bench_compositional.py"),
            "--in-process",
            "--out",
            str(paths["compositional"]),
        ],
        "latency_m5": [
            py,
            str(ROOT / "scripts" / "bench" / "latency_m5.py"),
            "--out",
            str(paths["latency_m5"]),
        ],
        "mouth_leak": [
            py,
            str(ROOT / "scripts" / "bench" / "mouth_leak.py"),
            "--out",
            str(paths["mouth_leak"]),
        ],
    }

    base = os.getenv("RESILEOS_BASE_URL", "http://127.0.0.1:8000/api/v1")
    http_up = _http_listening(base)
    runs = {}
    failures = []
    for name, cmd in commands.items():
        result = _run(cmd)
        runs[name] = result
        if result["exit_code"] != 0:
            failures.append(name)
            print(f"{name}: exit {result['exit_code']}", file=sys.stderr)
            if result["stderr_tail"]:
                print(result["stderr_tail"], file=sys.stderr)

    memory = _read(paths["memory_vs_llm"]) or {}
    equal = _read(paths["equal_budget"]) or {}
    temporal = _read(paths["temporal_probe"]) or {}
    composition = _read(paths["compositional"]) or {}
    latency = _read(paths["latency_m5"]) or {}
    mouth = _read(paths["mouth_leak"]) or {}
    resileos = memory.get("resileos") or {}
    llm = memory.get("llm_baseline") or {}
    comp = composition.get("resileos") or {}

    index = {
        "measured_at": utc_now(),
        "environment": environment(),
        "scope": (
            "Exact recall, abstention, residual consistency under the "
            "equal-budget hierarchy path, temporal conflict, and "
            "in-process ask/chain latency. Not generation, coding, or "
            "general reasoning."
        ),
        "artifacts": {name: str(path.relative_to(ROOT)) for name, path in paths.items()},
        "runs": {name: {"exit_code": row["exit_code"]} for name, row in runs.items()},
        "memory_vs_llm": {
            "backend": resileos.get("backend"),
            "exact_match_rate": resileos.get("exact_match_rate"),
            "invent_rate": resileos.get("invent_rate"),
            "abstain_rate": resileos.get("abstain_rate"),
            "n_known": resileos.get("n_known"),
            "n_unknown": resileos.get("n_unknown"),
            "p50_latency_ms_known": resileos.get("p50_latency_ms_known"),
            "mean_latency_ms_known": resileos.get("mean_latency_ms_known"),
            "llm_status": llm.get("status"),
            "llm_exact_match_rate": llm.get("exact_match_rate"),
            "llm_invent_rate": llm.get("invent_rate"),
            "llm_reason": llm.get("reason"),
        },
        "equal_budget": {
            "n_tasks": equal.get("n_tasks"),
            "budget_steps": equal.get("budget_steps"),
            "residual_false_accepts": (equal.get("residual") or {}).get("false_accepts"),
            "hierarchy_false_accepts": (equal.get("hierarchy") or {}).get("false_accepts"),
            "residual_accuracy": (equal.get("residual") or {}).get("accuracy"),
            "hierarchy_accuracy": (equal.get("hierarchy") or {}).get("accuracy"),
            "hierarchy_cycle_consistent": (equal.get("hierarchy") or {}).get(
                "cycle_consistent"
            ),
            "hierarchy_cycle_observed": (equal.get("hierarchy") or {}).get(
                "cycle_observed"
            ),
            "hierarchy_cycle_verified": (equal.get("hierarchy") or {}).get(
                "cycle_verified"
            ),
            "hierarchy_cycle_reasons": (equal.get("hierarchy") or {}).get(
                "cycle_reasons"
            ),
        },
        "temporal": {
            "pass": temporal.get("pass"),
            "reference_m9": (temporal.get("reference") or {}).get("M9"),
            "reference_conflicts": (temporal.get("reference") or {}).get("conflicts"),
            "reference_checks": (temporal.get("reference") or {}).get("checks"),
            "synthetic_pass": (temporal.get("synthetic_overlap") or {}).get("pass"),
            "overlap_detected": (temporal.get("synthetic_overlap") or {}).get(
                "conflicts_detected"
            ),
            "non_overlap_singular": (temporal.get("synthetic_overlap") or {}).get(
                "non_overlap_singular"
            ),
        },
        "composition": {
            "transport": comp.get("transport"),
            "http_status": (composition.get("http") or {}).get("status"),
            "composition_rate": comp.get("composition_rate"),
            "hits": comp.get("hits"),
            "total": comp.get("total"),
            "http_server_listening": http_up,
        },
        "m5_latency": {
            "transport": latency.get("transport"),
            "ask": latency.get("ask"),
            "chain": latency.get("chain"),
        },
        "m7_mouth_leak": {
            "leak_count": mouth.get("leak_count"),
            "target_leak_count": mouth.get("target_leak_count"),
            "require_verified_default": mouth.get("require_verified_default"),
            "spoken_text_when_unverified": (mouth.get("spoken") or {}).get(
                "spoken_text_when_unverified"
            ),
            "factual_prose_when_unverified": (mouth.get("spoken") or {}).get(
                "factual_prose_when_unverified"
            ),
            "writer_token_in_text_when_unverified": (mouth.get("spoken") or {}).get(
                "writer_token_in_text_when_unverified"
            ),
            "preference_echo_when_unverified": (mouth.get("spoken") or {}).get(
                "preference_echo_when_unverified"
            ),
        },
        "skipped": [
            {
                "name": "M6 5k-fact corpus",
                "reason": (
                    "Skipped. scripts/generate_scaled_facts.py can build a "
                    "deterministic corpus, but this run does not generate "
                    "or commit a 5k-fact fixture and does not seed it into "
                    "Titanos. M6 is unmeasured."
                ),
            },
            {
                "name": "composition HTTP",
                "reason": (
                    "The HTTP compositional script was not aimed at a live "
                    "server. RESILEOS_BASE_URL "
                    + ("was accepting connections." if http_up else "was not accepting connections.")
                    + " The in-process Titanos leg is the recorded composition sample."
                ),
            },
            {
                "name": "M5 HTTP",
                "reason": (
                    "p50/p95 are in-process method calls, not HTTP requests. "
                    "No API server was started."
                ),
            },
        ],
        "not_claimed": [
            "generation quality",
            "fluent coding",
            "general reasoning",
            "superiority to an LLM on any unmeasured dimension",
        ],
    }
    if llm.get("status") == "skipped":
        index["skipped"].append(
            {
                "name": "LLM baseline",
                "reason": llm.get("reason") or "LLM leg skipped",
            }
        )
    out = dated_artifact("measurement", day)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = redact_text(json.dumps(index, indent=2)) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
