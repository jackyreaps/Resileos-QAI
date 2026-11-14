"""Run the Lean checker on one user file, in a locked-down subprocess.

Plain results:
  CHECKED      the file compiles with no errors and no ``sorry``
  INCOMPLETE   it compiles, but a declaration uses ``sorry``
  FAILED       Lean reported an error (first error line and message)
  DECLINED     the file runs code (#eval, IO, extern, ...), which is not allowed
  UNAVAILABLE  Lean is not installed, or the sandbox can't be set up
  TIMEOUT      the check ran past its time limit

Nothing here learns, writes to Titanos, or changes ``require_verified``.
A pass is reported only when Lean itself exits 0 with no error or sorry.

Limits (env overrides, clamped):
  RESILEOS_LEAN_TIMEOUT_S     wall-clock seconds, default 60 (max 300)
  RESILEOS_LEAN_MEMORY_MB     Lean's own --memory limit, default 2048 (max 8192)
  RESILEOS_LEAN_MAX_BYTES     source size, default 200000
  RESILEOS_LEAN_BIN           path to ``lean`` (default: first on PATH)
  RESILEOS_LEAN_PROJECT       optional lake project dir; runs ``lake env lean``
  RESILEOS_LEAN_NETWORK       "isolate" (default) needs ``unshare -rn`` to work;
                              "off" lets an operator run without a network
                              namespace when the container itself has no network.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

FILE_NAME = "Proof.lean"

# Code that would execute during elaboration. Proof checking never needs it.
_DECLINED = [
    (re.compile(r"#eval\b"), "#eval"),
    (re.compile(r"#exit\b"), "#exit"),
    (re.compile(r"\brun_cmd\b|#run_cmd\b|\brun_elab\b|\brun_meta\b|#run\b"), "run_cmd"),
    (re.compile(r"\bIO\b|\bIO\."), "IO"),
    (re.compile(r"\bSystem\.|\bFS\.|\bProcess\b"), "system access"),
    (re.compile(r"(?:builtin_)?initialize\b"), "initialize"),
    (re.compile(r"@\[\s*(?:extern|implemented_by)\b|\bextern\b|\bimplemented_by\b"), "extern code"),
    (re.compile(r"\bunsafe\b"), "unsafe"),
    (re.compile(r"\bimport\s+Lake\b"), "import Lake"),
]
_DIAG = re.compile(r"^(?P<file>[^\n:]*?):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>error|warning|info)\s*:?\s*(?P<msg>.*)$")


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def limits() -> dict[str, int]:
    return {
        "timeout_s": _int_env("RESILEOS_LEAN_TIMEOUT_S", 60, 1, 300),
        "memory_mb": _int_env("RESILEOS_LEAN_MEMORY_MB", 2048, 256, 8192),
        "max_bytes": _int_env("RESILEOS_LEAN_MAX_BYTES", 200_000, 1_000, 2_000_000),
    }


def lean_binary() -> str | None:
    explicit = os.getenv("RESILEOS_LEAN_BIN", "").strip()
    if explicit:
        return explicit if os.access(explicit, os.X_OK) else None
    return shutil.which("lean")


def _netns_prefix() -> list[str] | None:
    """Command prefix that drops network access, or None if unavailable."""
    mode = os.getenv("RESILEOS_LEAN_NETWORK", "isolate").strip().lower()
    if mode == "off":
        return []
    unshare = shutil.which("unshare")
    if not unshare:
        return None
    try:
        probe = subprocess.run([unshare, "-rn", "true"], capture_output=True, timeout=5, check=False)
    except Exception:
        return None
    return [unshare, "-rn"] if probe.returncode == 0 else None


def declined_reason(source: str) -> str | None:
    for pattern, label in _DECLINED:
        match = pattern.search(source)
        if match:
            line = source.count("\n", 0, match.start()) + 1
            return f"line {line} uses {label}, which runs code. Proof checks can't run code."
    return None


def looks_like_lean(text: str) -> bool:
    body = str(text or "")
    if "```lean" in body:
        return True
    return bool(re.search(r"^\s*(theorem|lemma|example|def|import)\b[\s\S]*:=", body, re.M)) and (
        ":=" in body and ("by" in body or "theorem" in body or "lemma" in body)
    )


def extract_lean(text: str) -> str:
    """Pull the Lean code out of a chat message (a ```lean block, or the whole text)."""
    body = str(text or "")
    block = re.search(r"```lean\s*\n([\s\S]*?)```", body)
    if block:
        return block.group(1)
    start = re.search(r"^\s*(import|theorem|lemma|example|def|open|namespace|variable|set_option)\b", body, re.M)
    return body[start.start():] if start else body


def parse_diagnostics(output: str) -> list[dict[str, Any]]:
    diags: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in output.splitlines():
        match = _DIAG.match(raw.strip())
        if match and match.group("file").endswith(".lean"):
            current = {
                "line": int(match.group("line")),
                "column": int(match.group("col")),
                "severity": match.group("sev"),
                "message": match.group("msg").strip(),
            }
            diags.append(current)
        elif current is not None and raw.strip() and len(current["message"]) < 600:
            current["message"] = (current["message"] + "\n" + raw.rstrip()).strip()
    return diags


def _preexec(memory_mb: int, timeout_s: int):  # pragma: no cover - runs in the child
    def apply() -> None:
        import resource

        cpu = timeout_s + 5
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()

    return apply


def check_lean(source: str, *, filename: str = FILE_NAME) -> dict[str, Any]:
    """Check one Lean file. Returns a plain ``status`` plus raw output."""
    lim = limits()
    text = str(source or "")
    base = {"checker": "lean", "limits": lim, "network": "isolated", "learned": False}
    if not text.strip():
        return {**base, "status": "FAILED", "line": None, "summary": "The file is empty.", "raw": ""}
    if len(text.encode("utf-8")) > lim["max_bytes"]:
        return {**base, "status": "DECLINED", "summary": f"The file is larger than {lim['max_bytes']} bytes.", "raw": ""}
    reason = declined_reason(text)
    if reason:
        return {**base, "status": "DECLINED", "summary": "Not checked: " + reason, "raw": ""}
    lean = lean_binary()
    if not lean:
        return {
            **base,
            "status": "UNAVAILABLE",
            "summary": "Proof checking isn't set up on this server yet (Lean is not installed).",
            "raw": "",
        }
    prefix = _netns_prefix()
    if prefix is None:
        return {
            **base,
            "status": "UNAVAILABLE",
            "summary": "Proof checking is switched off: the server can't run Lean without network access.",
            "raw": "unshare -rn is not available; set RESILEOS_LEAN_NETWORK=off only if the container has no network.",
        }
    if not prefix:
        base["network"] = "container"
    with tempfile.TemporaryDirectory(prefix="lean-check-") as tmp:
        path = Path(tmp) / FILE_NAME
        path.write_text(text, encoding="utf-8")
        project = os.getenv("RESILEOS_LEAN_PROJECT", "").strip()
        if project:
            lake = str(Path(lean).with_name("lake")) if Path(lean).with_name("lake").exists() else (shutil.which("lake") or "lake")
            cmd = [*prefix, lake, "env", lean, f"--memory={lim['memory_mb']}", str(path)]
            cwd = project
        else:
            cmd = [*prefix, lean, f"--memory={lim['memory_mb']}", str(path)]
            cwd = tmp
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tmp,
            "LANG": "C.UTF-8",
        }
        for key in ("ELAN_HOME", "LEAN_PATH", "LEAN_SYSROOT"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        if "ELAN_HOME" not in env:
            # elan's `lean` shim finds toolchains under ~/.elan; HOME is a
            # throwaway dir here, so point it at the real one when present.
            elan_home = Path(os.path.expanduser("~")) / ".elan"
            if elan_home.is_dir():
                env["ELAN_HOME"] = str(elan_home)
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=lim["timeout_s"],
                check=False,
                stdin=subprocess.DEVNULL,
                preexec_fn=_preexec(lim["memory_mb"], lim["timeout_s"]),
            )
        except subprocess.TimeoutExpired:
            return {**base, "status": "TIMEOUT", "summary": f"Stopped after {lim['timeout_s']} seconds.", "raw": ""}
        except OSError as exc:
            return {**base, "status": "UNAVAILABLE", "summary": "Lean couldn't be started on this server.", "raw": type(exc).__name__}
    raw = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).replace(tmp, "")[-8000:]
    diags = parse_diagnostics(raw)
    errors = [d for d in diags if d["severity"] == "error"]
    sorries = [d for d in diags if d["severity"] == "warning" and "sorry" in d["message"]]
    result = {**base, "exit_code": proc.returncode, "diagnostics": diags[:50], "raw": raw}
    if errors:
        first = errors[0]
        message = first["message"].splitlines()[0][:300]
        return {**result, "status": "FAILED", "line": first["line"], "summary": f"Fails at line {first['line']}: {message}"}
    if proc.returncode != 0:
        return {**result, "status": "FAILED", "line": None, "summary": "Lean stopped with an error (see details)."}
    if sorries:
        return {**result, "status": "INCOMPLETE", "line": sorries[0]["line"], "summary": f"Not finished: line {sorries[0]['line']} uses sorry."}
    return {**result, "status": "CHECKED", "line": None, "summary": "Proof checks."}
