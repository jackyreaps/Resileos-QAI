"""Tests for the agent loop."""
from resileos.ui.agent_loop import run_task


def test_default_plan_runs():
    out = run_task("status")
    assert out["steps"] >= 1
    assert "trace" in out


def test_custom_plan():
    out = run_task("check", steps=[{"tool": "web_search", "args": {"query": "lean"}}])
    assert out["ok"] is True
    assert out["trace"][0]["tool"] == "web_search"
