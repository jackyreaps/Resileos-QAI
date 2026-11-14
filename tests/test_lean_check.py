"""Lean checker: plain results, hard limits, and never a fake pass."""
from __future__ import annotations

import os
import shutil
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from resileos.verify import lean_check as lc


FAKE_LEAN = textwrap.dedent(
    """\
    #!{python}
    import sys, time
    args = sys.argv[1:]
    assert any(a.startswith("--memory=") for a in args), args
    path = args[-1]
    src = open(path).read()
    if "SLEEP" in src:
        time.sleep(30)
    if "rfl_bad" in src:
        print(path + ":3:2: error: The rfl tactic failed.")
        print("  1 + 1 = 3")
        sys.exit(1)
    if "sorry" in src:
        print(path + ":2:8: warning: declaration uses 'sorry'")
        sys.exit(0)
    if "CRASH" in src:
        sys.exit(2)
    sys.exit(0)
    """
)


@pytest.fixture
def fake_lean(tmp_path, monkeypatch):
    path = tmp_path / "lean"
    path.write_text(FAKE_LEAN.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("RESILEOS_LEAN_BIN", str(path))
    monkeypatch.setenv("RESILEOS_LEAN_NETWORK", "off")
    return path


def test_unavailable_without_lean(monkeypatch):
    monkeypatch.setenv("RESILEOS_LEAN_BIN", "/nonexistent/lean")
    out = lc.check_lean("theorem t : 1 = 1 := rfl\n")
    assert out["status"] == "UNAVAILABLE"
    assert "isn't set up" in out["summary"]
    assert out["learned"] is False


def test_unavailable_when_network_cannot_be_isolated(fake_lean, monkeypatch):
    monkeypatch.setenv("RESILEOS_LEAN_NETWORK", "isolate")
    monkeypatch.setattr(lc.shutil, "which", lambda name: None)
    out = lc.check_lean("theorem t : 1 = 1 := rfl\n")
    assert out["status"] == "UNAVAILABLE"
    assert "network" in out["summary"]


def test_pass_fail_sorry_and_crash(fake_lean):
    ok = lc.check_lean("theorem t : 1 = 1 := rfl\n")
    assert ok["status"] == "CHECKED" and ok["summary"] == "Proof checks."
    bad = lc.check_lean("theorem t : 1 + 1 = 3 := by\n  -- rfl_bad\n  rfl\n")
    assert bad["status"] == "FAILED"
    assert bad["line"] == 3
    assert bad["summary"].startswith("Fails at line 3: The rfl tactic failed.")
    assert "rfl tactic failed" in bad["raw"]
    assert str(Path("/tmp")) not in bad["raw"] or "lean-check-" not in bad["raw"]
    sorry = lc.check_lean("theorem s (n : Nat) : n + 0 = n := by\n  sorry\n")
    assert sorry["status"] == "INCOMPLETE" and sorry["line"] == 2
    crash = lc.check_lean("-- CRASH\n")
    assert crash["status"] == "FAILED"


def test_timeout_limit(fake_lean, monkeypatch):
    monkeypatch.setenv("RESILEOS_LEAN_TIMEOUT_S", "1")
    out = lc.check_lean("-- SLEEP\n")
    assert out["status"] == "TIMEOUT"
    assert out["limits"]["timeout_s"] == 1


@pytest.mark.parametrize(
    "source",
    [
        '#eval IO.println "hi"',
        "def f : IO Unit := pure ()",
        "@[extern \"x\"] opaque g : Nat",
        "unsafe def h : Nat := 0",
        "initialize foo : IO.Ref Nat ← IO.mkRef 0",
        "run_cmd pure ()",
    ],
)
def test_code_that_runs_is_declined(fake_lean, source):
    out = lc.check_lean(source + "\n")
    assert out["status"] == "DECLINED"
    assert "can't run code" in out["summary"]


def test_limits_are_clamped(monkeypatch):
    monkeypatch.setenv("RESILEOS_LEAN_TIMEOUT_S", "99999")
    monkeypatch.setenv("RESILEOS_LEAN_MEMORY_MB", "1")
    lim = lc.limits()
    assert lim["timeout_s"] == 300
    assert lim["memory_mb"] == 256


def test_size_limit(fake_lean, monkeypatch):
    monkeypatch.setenv("RESILEOS_LEAN_MAX_BYTES", "1000")
    out = lc.check_lean("-- " + "x" * 2000)
    assert out["status"] == "DECLINED"


def test_pasted_proof_detection():
    msg = "can you check this?\n```lean\ntheorem t : 1 = 1 := rfl\n```"
    assert lc.looks_like_lean(msg)
    assert lc.extract_lean(msg).strip() == "theorem t : 1 = 1 := rfl"
    assert not lc.looks_like_lean("What is the domain of Zeus?")


def test_require_verified_is_untouched():
    text = Path(lc.__file__).read_text(encoding="utf-8")
    assert "require_verified =" not in text
    assert ".learn(" not in text


@pytest.mark.skipif(not (os.getenv("RESILEOS_LEAN_BIN") or shutil.which("lean")), reason="Lean is not installed")
def test_real_lean_when_installed(monkeypatch):
    if not os.getenv("RESILEOS_LEAN_BIN") and not shutil.which("lean"):
        pytest.skip("no lean")
    ok = lc.check_lean("theorem two : 1 + 1 = 2 := by rfl\n")
    if ok["status"] == "UNAVAILABLE":
        pytest.skip(ok["summary"])
    assert ok["status"] == "CHECKED"
    bad = lc.check_lean("theorem t : 1 + 1 = 3 := by\n  rfl\n")
    assert bad["status"] == "FAILED" and bad["line"] == 2
