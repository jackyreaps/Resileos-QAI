"""Agent loop: chain tools until a task is done.

This is the step from a tool set to a system that finishes work.
It searches, reads, edits, tests, and can commit, then records the result.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.worker_tools import (
    apply_diff,
    diagnostics,
    fetch_url,
    git_commit,
    git_status,
    read_file,
    run_tests,
    search_repo,
    web_search,
    write_file,
)


def run_task(
    goal: str,
    *,
    steps: Optional[list[dict[str, Any]]] = None,
    on_step: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Run a planned sequence of tool steps toward a goal.

    Each step is {tool, args}. Tools are the worker set.
    Returns the trace and whether the last step succeeded.
    """
    plan = steps or _default_plan(goal)
    trace = []
    ok = True
    for step in plan:
        result = _call(step["tool"], step.get("args", {}))
        row = {"tool": step["tool"], "ok": result.get("ok", True), "result": result}
        trace.append(row)
        if on_step:
            on_step(row)
        if not row["ok"]:
            ok = False
            break
    return {"goal": goal, "ok": ok, "steps": len(trace), "trace": trace}


def _default_plan(goal: str) -> list[dict[str, Any]]:
    """A simple plan: search, then note the goal."""
    return [
        {"tool": "web_search", "args": {"query": goal}},
        {"tool": "search_repo", "args": {"query": goal.split()[0] if goal else ""}},
    ]


def _call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    table = {
        "web_search": web_search,
        "search_repo": search_repo,
        "fetch_url": fetch_url,
        "read_file": read_file,
        "write_file": write_file,
        "apply_diff": apply_diff,
        "run_tests": run_tests,
        "diagnostics": diagnostics,
        "git_status": git_status,
        "git_commit": git_commit,
    }
    fn = table.get(tool)
    if fn is None:
        return {"ok": False, "error": f"unknown tool {tool}"}
    try:
        out = fn(**args)
        if isinstance(out, dict) and "ok" not in out:
            out = {"ok": True, **out} if isinstance(out, dict) else {"ok": True, "result": out}
        return out if isinstance(out, dict) else {"ok": True, "result": out}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
