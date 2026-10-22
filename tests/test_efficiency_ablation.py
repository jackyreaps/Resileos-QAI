"""Smoke test for the efficiency ablation (Hardened Roadmap 1.1)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_efficiency_ablation.py"


def test_ablation_script_exists():
    assert SCRIPT.exists(), f"missing {SCRIPT}"


def test_ablation_runs_and_writes_report(tmp_path):
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--steps", "40", "--eval-every", "10",
         "--target-delta", "0.001", "--seed", "0",
         "--out", str(out)],
        capture_output=True, text=True, timeout=600,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out.exists()
    rep = json.loads(out.read_text())

    for key in ("baseline_nll_no_modulation", "modes", "k_steps",
                "k_flops_est", "k_wall_toy_unreliable", "verdict"):
        assert key in rep, f"missing {key}"

    assert "nll" in rep["modes"]
    assert "framework" in rep["modes"]
    for mode in ("nll", "framework"):
        assert "flops_per_step_est" in rep["modes"][mode]
        assert "cost_breakdown_seconds" in rep["modes"][mode]
        assert rep["modes"][mode]["flops_per_step_est"] > 0

    assert rep["verdict"] in (
        "not reached",
        "viable: framework-native is materially more efficient",
        "marginal: savings do not justify framework complexity",
        "falsified: framework-native is not more efficient "
        "per unit compute; revert to MoE-only",
    )


def test_ablation_rejects_bad_topics():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--steps", "2", "--r", "4",
         "--n-topics", "8"],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert proc.returncode != 0
    assert "n-topics" in proc.stderr
