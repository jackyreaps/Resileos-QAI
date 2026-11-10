"""Regression tests for the RES-332 review findings."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_kin_package_imports_and_hades_collects():
    proc = subprocess.run(
        [sys.executable, "-c",
         "import resileos.kin as kin; "
         "from resileos.harness.harness_wrap import harness_wrap; "
         "assert kin.harness_wrap is harness_wrap; "
         "assert callable(kin.wire_perception)"],
        cwd="/tmp",
        env={
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "tests/test_hades.py", "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert collected.returncode == 0, collected.stderr[-2000:]
    assert "error" not in collected.stdout.lower()


def test_store_dates_round_trip_and_reject_bad(tmp_path):
    from resileos.titanos.store import _days_to_iso, _iso_to_days

    assert _iso_to_days(None) != -1
    assert _days_to_iso(_iso_to_days(None)) is None
    assert _days_to_iso(_iso_to_days("1969-12-31")) == "1969-12-31"
    assert _iso_to_days("1969-12-31") == -1
    assert _days_to_iso(_iso_to_days("476-01-01")) == "0476-01-01"
    with pytest.raises(ValueError):
        _iso_to_days("not-a-date")


def test_validity_uses_real_dates_and_offsets():
    from titanos import Titanos, TitanosConfig

    t = Titanos(TitanosConfig(dim=256, m=16, n=16, r=4, n_loops=2, seed=0))
    t.learn("Rome", "capital_of", "Roman Empire", valid_to="476-01-01")
    t.learn("City", "capital_of", "Early", valid_from="999-01-01", valid_to="1000-06-01")
    assert t.ask_list("Rome", "capital_of", as_of="100-01-01") == ["Roman Empire"]
    assert t.ask_list("Rome", "capital_of", as_of="500-01-01") == []
    assert t.ask_list("City", "capital_of", as_of="999") == ["Early"]
    assert t.ask_list("City", "capital_of", as_of="1000-01-01") == ["Early"]
    inside = t._fact_valid_at(
        ("Athens", "capital_of", "Ottoman", "1458-01-01", "1834-01-01"),
        "1833-12-31T23:00:00+02:00",
    )
    outside = t._fact_valid_at(
        ("Athens", "capital_of", "Ottoman", "1458-01-01", "1834-01-01"),
        datetime(1834, 1, 1, 0, 30, tzinfo=timezone.utc),
    )
    assert inside is True
    assert outside is False


def test_ask_as_of_returns_ottoman_and_filter_off_keeps_expired():
    from titanos import Titanos, TitanosConfig

    cfg = TitanosConfig(dim=256, m=16, n=16, r=4, n_loops=2, seed=0)
    t = Titanos(cfg)
    t.learn(
        "Athens", "capital_of", "Ottoman",
        valid_from="1458-01-01", valid_to="1834-01-01",
    )
    t.learn(
        "Athens", "capital_of", "Greece",
        valid_from="1834-01-01", valid_to=None,
    )
    historical = t.ask("Athens", "capital_of", as_of="1800-01-01")
    assert historical.status == "ACCEPTED"
    assert historical.value == "Ottoman"
    cfg.temporal_filter_current = False
    t2 = Titanos(cfg)
    t2.learn(
        "Athens", "capital_of", "Ottoman",
        valid_from="1458-01-01", valid_to="1834-01-01",
    )
    current = t2.ask("Athens", "capital_of")
    assert current.status == "ACCEPTED"
    assert current.value == "Ottoman"


def test_overlapping_bounded_facts_conflict():
    from titanos import Titanos, TitanosConfig

    t = Titanos(TitanosConfig(dim=256, m=16, n=16, r=4, n_loops=2, seed=0))
    t.learn("Athens", "capital_of", "A", valid_from="1800-01-01", valid_to="1900-01-01")
    t.learn("Athens", "capital_of", "B", valid_from="1850-01-01", valid_to="1920-01-01")
    ans = t.ask("Athens", "capital_of", as_of="1860-01-01")
    assert ans.status == "CONFLICT"
    assert ans.value is None
    assert t.ask_list("Athens", "capital_of", as_of="1860-01-01") == ["A", "B"]


def test_chain_threads_as_of():
    from titanos import Titanos, TitanosConfig

    t = Titanos(TitanosConfig(dim=256, m=16, n=16, r=4, n_loops=2, seed=0))
    t.learn("A", "next", "B", valid_from="1800-01-01", valid_to="1900-01-01")
    t.learn("B", "next", "C", valid_from="1800-01-01", valid_to="1900-01-01")
    t.learn("A", "next", "Z", valid_from="2000-01-01", valid_to=None)
    walked = t.chain("A", ["next", "next"], as_of="1850-01-01")
    assert walked.status == "ACCEPTED"
    assert walked.value == "C"


def test_zeus_records_decline_when_parent_is_none():
    from resileos.titanos.zeus import run_zeus_query

    class Child:
        name = "zeus"

    class Group:
        def select(self):
            return Child()

        def record(self, name, csi, accepted):
            self.logged = (name, csi, accepted)

        def evaluate_and_prune(self):
            pass

    group = Group()
    assert run_zeus_query(group, None, "A", "rel") is None
    assert group.logged[0] == "zeus"
    assert group.logged[2] is False


def test_equal_validity_bounds_are_rejected():
    from resileos.kin.verifiers import Claim, check_temporal

    claim = Claim(
        subject="A", relation="r", obj="B",
        valid_from="1800-01-01", valid_until="1800-01-01",
    )
    result = check_temporal(claim, {})
    assert result.ok is False
