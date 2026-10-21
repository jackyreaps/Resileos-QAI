"""Smoke tests for the diagnostic scripts (RES-304 / φ-compress).

These scripts are not part of the importable package; they live under
scripts/ and are run manually. Without a smoke test they can drift out
of API compatibility with the modules they import, which has already
happened twice in this project (n_visited() on OscillatorOrientedSearch
and a stale keyword on HierarchicalQuery.locate).

Each test imports the script's public function and asserts the module
loads. No simulation is run here; the full diagnostic runs are separate,
slower, and require report directories to be writable.
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _import_script(name: str):
    """Import a script by filename stem from scripts/.

    The scripts directory is not a package. Add it to sys.path, import
    the module, then remove the path entry so later imports are not
    affected.
    """
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
    """Optional: only if scripts/run_chsh_scan.py exists."""
    if not (SCRIPTS / "run_chsh_scan.py").exists():
        pytest.skip("run_chsh_scan.py not present")
    mod = _import_script("run_chsh_scan")
    assert hasattr(mod, "main") or hasattr(mod, "run")


def test_oriented_search_public_api():
    """Confirm the public API of OscillatorOrientedSearch matches what
    the diagnostic scripts call. This is the specific drift that caused
    the n_visited() bug.
    """
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
    """Confirm locate() keyword is target_hv, not target.

    The earlier failing test called locate(..., target=...) which was
    fixed to target_hv=. This test freezes the keyword so it cannot
    silently drift back.
    """
    import inspect
    from resileos.hierarchy.query import HierarchicalQuery

    sig = inspect.signature(HierarchicalQuery.locate)
    params = list(sig.parameters)
    assert "target_hv" in params, (
        f"HierarchicalQuery.locate parameters are {params}; "
        "expected target_hv"
    )
    assert "target" not in params, (
        "HierarchicalQuery.locate must not accept a bare `target` kwarg"
    )
