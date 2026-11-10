"""Coding tools for worlds, guild work, and Lean.

Workspace files under RESILEOS_WORKSPACE.
Lean, pytest, and repo search are hooks.
Web search uses the existing search path so the worker can look things up.
"""
from __future__ import annotations

import json
import math
import os
import shlex
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


def fetch_url(url: str, timeout: int = 20) -> dict[str, Any]:
    """Fetch a page and return text. Search is no longer only a link."""
    from urllib.request import urlopen
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read(200_000)
        text = raw.decode("utf-8", errors="ignore")
        return {"ok": True, "url": url, "text": text[:4000]}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def apply_diff(rel: str, old: str, new: str) -> dict[str, Any]:
    """Replace one occurrence of old with new in a workspace file."""
    p = _safe_path(rel)
    if not p.exists():
        return {"ok": False, "error": "missing"}
    text = p.read_text()
    if old not in text:
        return {"ok": False, "error": "old text not found"}
    p.write_text(text.replace(old, new, 1))
    return {"ok": True, "path": str(p)}


def git_status() -> dict[str, Any]:
    return run_shell("git status --short")


def git_diff() -> dict[str, Any]:
    return run_shell("git diff")


def git_commit(message: str) -> dict[str, Any]:
    if not str(message).strip():
        return {"ok": False, "error": "empty message"}
    if "\n" in message or "\x00" in message:
        return {"ok": False, "error": "invalid message"}
    add = _run_argv(["git", "add", "-A"])
    if not add.get("ok"):
        return add
    return _run_argv(["git", "commit", "-m", message])


def guild_board(guild_id: str, title: str, body: str = "") -> dict[str, Any]:
    """A board item under a guild hub namespace."""
    return {
        "subject": f"guild:{guild_id}",
        "relation": "board",
        "obj": title,
        "body": body,
        "status": "open",
    }


def guild_assign(guild_id: str, title: str, member: str) -> dict[str, Any]:
    """Assign a board item to a member."""
    return {
        "subject": f"guild:{guild_id}",
        "relation": "assigned",
        "obj": f"{title} -> {member}",
    }


def record_merit(
    guild_id: str,
    member: str,
    artifact: str,
    *,
    evidence: str = "",
    score: int = 1,
) -> dict[str, Any]:
    """A completed board task as a merit candidate.

    Matches the guild-system attestation shape closely enough to learn
    into a guild hub. Signature and key stay with the guild process.
    """
    return {
        "subject": f"guild:{guild_id}",
        "relation": "merit",
        "obj": f"{member}:{artifact}",
        "attestation": {
            "issuer_guild": guild_id,
            "issuer_moniker": member,
            "artifact_ref": artifact,
            "verification_evidence": evidence,
            "score": int(score),
            "status": "candidate",
        },
    }


def complete_and_credit(
    guild_id: str,
    member: str,
    title: str,
    *,
    evidence: str = "",
) -> dict[str, Any]:
    """Finish a board item and emit a merit candidate."""
    board_item = guild_board(guild_id, title)
    merit = record_merit(guild_id, member, title, evidence=evidence)
    from resileos.ui.credits import earn_for_work
    credit = earn_for_work(member, title, amount=1)
    return {"board": board_item, "merit": merit, "credit": credit}


def run_next() -> dict[str, Any]:
    """Take the next queued task and run it."""
    open_tasks = board.open()
    if not open_tasks:
        return {"ok": False, "note": "no open tasks"}
    task = open_tasks[0]
    kind = task.get("kind")
    payload = task.get("payload", {})
    if kind == "worker":
        result = run_worker(payload.get("code", ""))
    elif kind == "learn":
        result = learn_into_hub(payload.get("facts", []))
    else:
        result = {"ok": False, "error": f"unknown kind {kind}"}
    board.complete(task["id"], result)
    return {"task": task["id"], "result": result}


def advance(steps: int = 3) -> list[dict[str, Any]]:
    """Run the next open tasks in order. This is the advance loop."""
    out = []
    for _ in range(max(1, steps)):
        if not board.open():
            break
        out.append(run_next())
    return out


_GIT_ALLOWED = {
    "status": lambda args: args in ([], ["--short"]),
    "diff": lambda args: args == [],
    "log": lambda args: args == [] or args == ["--oneline"],
    "add": lambda args: args == ["-A"],
    "commit": lambda args: len(args) == 2 and args[0] == "-m",
}


def _argv_from(cmd: str | list | tuple) -> list[str]:
    if isinstance(cmd, (list, tuple)):
        return [str(part) for part in cmd]
    return shlex.split(str(cmd), posix=True)


def _argv_allowed(argv: list[str]) -> str | None:
    """Allowlisted git invocations. No shell."""
    if not argv:
        return "empty command"
    if Path(argv[0]).name != "git":
        return "command not allowed"
    if len(argv) < 2 or argv[1] not in _GIT_ALLOWED:
        return "git subcommand not allowed"
    if not _GIT_ALLOWED[argv[1]](argv[2:]):
        return "git arguments not allowed"
    return None


def _run_argv(argv: list[str], timeout: int = 60) -> dict[str, Any]:
    reason = _argv_allowed(argv)
    if reason:
        return {"ok": False, "error": reason}
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE),
        )
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "out": proc.stdout[-800:],
            "err": proc.stderr[-400:],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_shell(cmd: str | list | tuple, timeout: int = 60) -> dict[str, Any]:
    """Run an allowlisted argv in the workspace. Never uses a shell."""
    try:
        argv = _argv_from(cmd)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return _run_argv(argv, timeout=timeout)


_HUB = None


def hub_workbench():
    """Small in-process hub. Not the live API store."""
    global _HUB
    if _HUB is None:
        from resileos.answer.workbench import Workbench
        from titanos import Titanos, TitanosConfig
        titan = Titanos(TitanosConfig(
            dim=256, m=16, n=16, r=4, n_loops=2, seed=0, use_attractor=False,
        ))
        _HUB = Workbench(titan=titan)
    return _HUB


def _hub_triples(facts: list) -> list[tuple[str, str, str]]:
    rows = []
    for fact in facts or []:
        if isinstance(fact, dict):
            subject = fact.get("subject")
            relation = fact.get("relation")
            obj = fact.get("obj", fact.get("object"))
        else:
            subject, relation, obj = fact
        subject, relation, obj = str(subject), str(relation), str(obj)
        if not subject.startswith(("user:", "world:", "org:")):
            subject = f"world:{subject}"
        rows.append((subject, relation, obj))
    return rows


def learn_into_hub(facts: list) -> dict[str, Any]:
    """Write queued facts into the hub workbench."""
    from resileos.answer.hub_train import train_hub
    triples = _hub_triples(facts)
    if not triples:
        return {"ok": True, "learned": 0, "subjects": []}
    try:
        n = train_hub(hub_workbench(), triples, require_hub_prefix=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "learned": 0}
    subjects = sorted({s for s, _, _ in triples})
    return {"ok": True, "learned": n, "subjects": subjects}


def diagnostics(rel: str) -> dict[str, Any]:
    """Syntax and Lean diagnostics for a file. LSP-lite."""
    p = _safe_path(rel)
    if not p.exists():
        return {"ok": False, "error": "missing"}
    if p.suffix == ".py":
        try:
            compile(p.read_text(), str(p), "exec")
            return {"ok": True, "kind": "python", "note": "syntax ok"}
        except SyntaxError as exc:
            return {"ok": False, "kind": "python", "error": str(exc), "line": exc.lineno}
    if p.suffix == ".lean":
        return lean_check(rel)
    return {"ok": True, "kind": p.suffix, "note": "no checker"}


def edit_files(edits: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Multi-file write. Each item: {path, content}."""
    out = []
    for e in edits:
        try:
            path = write_file(e["path"], e["content"])
            out.append({"path": path, "ok": True})
        except Exception as exc:
            out.append({"path": e.get("path"), "ok": False, "error": str(exc)})
    return out


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
    "web_search": web_search, "fetch_url": fetch_url, "apply_diff": apply_diff,
    "git_status": git_status, "git_diff": git_diff, "git_commit": git_commit,
    "guild_board": guild_board, "guild_assign": guild_assign,
    "record_merit": record_merit, "complete_and_credit": complete_and_credit,
    "run_next": run_next, "advance": advance,
    "run_shell": run_shell, "diagnostics": diagnostics, "edit_files": edit_files,
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
