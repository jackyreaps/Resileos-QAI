"""Task API helper.

Wraps the task loop for a FastAPI route.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.task_loop import run_task


def task_from_steps(
    goal: str,
    steps: list[dict[str, str]],
    ask: Callable[[str, str], Any],
    mouth_fn: Optional[Any] = None,
) -> dict[str, Any]:
    pairs = [(s["subject"], s["relation"]) for s in steps if "subject" in s and "relation" in s]
    return run_task(goal, ask=ask, steps=pairs, mouth_fn=mouth_fn)
