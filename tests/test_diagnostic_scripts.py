"""Smoke tests for the diagnostic scripts (RES-304 / RES-403).

These scripts live under scripts/ and are run manually. Without a smoke
test they drift out of API compatibility with the modules they import.
That has already happened twice in this project: OscillatorOrientedSearch
.n_visited() (a method that does not exist) and HierarchicalQuery.locate
called with a bare `target` keyword.

Each test imports the script's module and asserts the public API the
scripts call is still present. No simulation is run.
"""
import importlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _import_script(name: str):
    inserted = False
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
        inserted = True
    try:
        return importlib.import_module(name)
    finally:
        if inserted:
            try:
                sys.path.remove(str(SCRIPTS))
            except ValueError:
                pass


def test_run_evolution_ab_imports():
    mod = _import_script("run_evolution_ab")
    assert hasattr(mod, "main") or hasattr(mod, "run"), (
        "run_evolution_ab must expose main() or run()"
    )


def test_run_directional_diagnostic_imports():
    mod = _import_script("run_directional_diagnostic")
    assert hasattr(mod, "main") or hasattr(mod, "run"), (
        "run_directional_diagnostic must expose main() or run()"
    )


def test_run_chsh_scan_imports():
    if not (SCRIPTS / "run_chsh_scan.py").exists():
        pytest.skip("run_chsh_scan.py not present")
    mod = _import_script("run_chsh_scan")
    assert hasattr(mod, "main") or hasattr(mod, "run")


def test_oriented_search_public_api():
    """The specific drift that caused the n_visited() bug."""
    from resileos.evolution_oscillator import OscillatorOrientedSearch

    for name in ("run", "best", "best_so_far", "history", "coverage", "summary"):
        assert hasattr(OscillatorOrientedSearch, name), (
            f"OscillatorOrientedSearch missing public method {name}"
        )
    assert not hasattr(OscillatorOrientedSearch, "n_visited"), (
        "OscillatorOrientedSearch.n_visited no longer exists; update "
        "scripts/run_evolution_ab.py to use len(_visited)"
    )


def test_hierarchical_query_locate_signature():
    """The specific drift that caused the last test failure."""
    from resileos.hierarchy.query import HierarchicalQuery

    params = list(inspect.signature(HierarchicalQuery.locate).parameters)
    assert "target_hv" in params, (
        f"HierarchicalQuery.locate parameters are {params}; "
        "expected target_hv"
    )
    assert "target" not in params, (
        "HierarchicalQuery.locate must not accept a bare `target` kwarg"
    )
