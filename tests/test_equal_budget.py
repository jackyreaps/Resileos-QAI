"""Equal-budget helper: same tasks, same step cap, two paths."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bench.equal_budget import DEFAULT_BUDGET, run_equal_budget


def test_equal_budget_respects_the_shared_step_cap(tmp_path):
    facts = Path(__file__).resolve().parents[1] / "configs" / "titanos-facts.json"
    report = run_equal_budget(
        facts_path=facts,
        budget_steps=DEFAULT_BUDGET,
        hades_dir=tmp_path / "hades",
    )
    assert report["budget_steps"] == DEFAULT_BUDGET
    for name in ("residual", "hierarchy"):
        block = report[name]
        assert 0.0 <= block["accuracy"] <= 1.0
        assert 0.0 <= block["correct_abstain_rate"] <= 1.0
        assert block["false_accepts"] >= 0
        assert block["steps_max"] <= DEFAULT_BUDGET
        assert block["steps_mean"] <= DEFAULT_BUDGET
        assert block["latency_ms_total"] >= 0.0
    assert report["residual"]["false_accepts"] == 0
    assert report["hierarchy"]["false_accepts"] == 0
    # The hierarchy path spends more of the same budget.
    assert report["hierarchy"]["steps_mean"] > report["residual"]["steps_mean"]


def test_equal_budget_zero_steps_abstains(tmp_path):
    facts = Path(__file__).resolve().parents[1] / "configs" / "titanos-facts.json"
    report = run_equal_budget(
        facts_path=facts,
        budget_steps=0,
        hades_dir=tmp_path / "hades",
    )
    assert report["residual"]["steps_max"] == 0
    assert report["hierarchy"]["steps_max"] == 0
    assert report["residual"]["false_accepts"] == 0
    assert report["hierarchy"]["false_accepts"] == 0
    # With no steps, known facts cannot be answered.
    assert report["residual"]["accuracy"] < 1.0
