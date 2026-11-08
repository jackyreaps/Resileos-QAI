"""Coding tools for worlds, guild work, and Lean.

Workspace files under RESILEOS_WORKSPACE.
Lean, pytest, and repo search are hooks.
Web search uses the existing search path so the worker can look things up.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import numpy as np

from resileos.ui.offline_tasks import TaskBoard, queue_learn, queue_worker
from resileos.ui.search_flow import web_search_url

WORKSPACE = Path(os.getenv("RESILEOS_WORKSPACE", "workspace")).resolve()


def _safe_path(rel: str) -> Path:
    p = (WORKSPACE / rel).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError("path escapes workspace")
    return p


def read_file(rel: str) -> str:
    return _safe_path(rel).read_text()


def write_file(rel: str, content: str) -> str:
    p = _safe_path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return str(p)


def list_files(rel: str = ".") -> list[str]:
    root = _safe_path(rel)
    if not root.exists():
        return []
    return [str(p.relative_to(WORKSPACE)) for p in root.rglob("*") if p.is_file()][:200]


def search_repo(query: str, rel: str = ".") -> list[dict[str, Any]]:
    """Find lines in the workspace that contain the query."""
    hits = []
    root = _safe_path(rel)
    if not root.exists():
        return hits
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in {".py", ".md", ".lean", ".txt", ".json"}:
            continue
        try:
            for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                if query in line:
                    hits.append({"file": str(p.relative_to(WORKSPACE)), "line": i, "text": line[:160]})
                    if len(hits) >= 40:
                        return hits
        except Exception:
            continue
    return hits


def run_tests(rel: str = "tests") -> dict[str, Any]:
    """Run pytest on a workspace path."""
    p = _safe_path(rel)
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", str(p), "-q", "--tb=line"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(WORKSPACE),
        )
        return {"ok": proc.returncode == 0, "code": proc.returncode, "out": proc.stdout[-800:]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def lean_check(rel: str) -> dict[str, Any]:
    p = _safe_path(rel)
    try:
        proc = subprocess.run(["lean", str(p)], capture_output=True, text=True, timeout=60)
        return {"ok": proc.returncode == 0, "code": proc.returncode, "out": proc.stdout[-500:], "err": proc.stderr[-500:]}
    except FileNotFoundError:
        return {"ok": False, "note": "lean not on PATH"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def web_search(query: str) -> dict[str, Any]:
    """Search URL for a query. Uses the same path as Studio search."""
    return {"query": query, "url": web_search_url(query)}


def grid(rows: int, cols: int, fill: float = 0.0) -> np.ndarray:
    return np.full((int(rows), int(cols)), fill, dtype=np.float32)


def scene(name: str, **props: Any) -> dict[str, Any]:
    return {"name": name, "props": props}


def _limited_import(name, *a, **k):
    allowed = ("numpy", "math", "json", "pathlib")
    if name in allowed or name.startswith("numpy."):
        return __import__(name, *a, **k)
    raise ImportError(name)


_SAFE = {
    "np": np, "numpy": np, "math": math, "json": json,
    "abs": abs, "min": min, "max": max, "sum": sum, "len": len, "range": range,
    "list": list, "dict": dict, "str": str, "int": int, "float": float,
    "grid": grid, "scene": scene,
    "read_file": read_file, "write_file": write_file, "list_files": list_files,
    "search_repo": search_repo, "run_tests": run_tests, "lean_check": lean_check,
    "web_search": web_search,
}


def run_worker(code: str) -> dict[str, Any]:
    local: dict[str, Any] = {}
    glb = {"__builtins__": {"__import__": _limited_import}, **_SAFE}
    try:
        result = eval(code, glb, local)
        return {"ok": True, "result": _fmt(result), "kind": "expr"}
    except SyntaxError:
        pass
    except Exception as exc:
        return {"ok": False, "error": str(exc), "kind": "expr"}
    try:
        exec(code, glb, local)
        return {"ok": True, "result": _fmt(local.get("out", local)), "kind": "exec"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "kind": "exec"}


def _fmt(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return {"shape": list(value.shape), "dtype": str(value.dtype), "preview": value.flatten()[:8].tolist()}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    if isinstance(value, (list, dict)):
        return value
    return str(value)[:400]


board = TaskBoard()


def worker_with_task(code: str, *, note: str = "") -> dict[str, Any]:
    task = board.add(queue_worker(code, note=note))
    result = run_worker(code)
    board.complete(task["id"], result)
    return {"task": task["id"], "result": result, "open": len(board.open())}
