"""Demi-god temporary swarms live only for the summon."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import residual_consistency
from resileos.kin.demigods import (
    DemigodError,
    DemigodHierarchyError,
    demigod_attempt,
    demigod_dismiss,
    demigod_duty,
    demigod_stop,
    demigod_summon,
    promote_temporary,
    swarm_surface,
)
from resileos.kin.hades import Hades
from resileos.kin.legions import LegionError, kin_catalogue, register_legion
from resileos.kin.moirai import checkpoint_allowed, get_coordination, reset_coordination
from resileos.kin.studio_tools import register_studio_legions


_EXTRAS = ("mark_reader", "iris_probe", "hold_group", "hold_pgid", "sneak")


@pytest.fixture(autouse=True)
def _clean_desk():
    reset_coordination()
    yield
    reset_coordination()
    from resileos.kin.demigods import swarm as swarm_mod
    from resileos.kin.legions import _surfaces

    swarm_mod._ATTEMPTS.clear()
    for name in _EXTRAS:
        for kin in ("hermes", "iris", "hades", "eat"):
            _surfaces.get(kin, {}).pop(name, None)


def _packet() -> ControlPacket:
    packet = ControlPacket(id="swarm-duty")
    packet.budget_remaining = {"steps": 5, "cost": 1.0, "tokens": 100}
    packet.evidence = []
    return packet


def _names(kin: str) -> set[str]:
    return {row["name"] for row in kin_catalogue(kin)}


def test_swarm_mounts_for_the_check_and_is_gone_after_dismiss(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    register_studio_legions()

    def mark_reader(seen, **kwargs):
        """Read one mark through the parent gate."""
        return {"mark": kwargs.get("mark"), "saw_history": "history" in seen}

    register_legion(
        "hermes",
        mark_reader,
        name="mark_reader",
        constraints={"action": "inspect", "writes_residual": False, "executes": True},
    )
    before = _names("hermes")
    packet = _packet()
    saved: dict = {}
    with demigod_attempt(
        "hephaestus",
        packet,
        swarm=["mark_reader", "joint_note", "forge_video"],
    ) as surface:
        assert set(surface) == {"mark_reader", "joint_note", "forge_video"}
        assert "demigod:hephaestus" in packet.guides_loaded
        assert "demigod_swarm" in packet.state
        assert _names("hermes") == before
        assert "joint_note" not in _names("hermes")
        assert "forge_video" not in _names("hades")
        with demigod_duty("hephaestus"):
            produced = surface["mark_reader"](packet, mark="served")
            note = surface["joint_note"](packet, note="temp")
            video = surface["forge_video"](packet, prompt="a hill")
            with pytest.raises(DemigodHierarchyError, match="cannot summon"):
                demigod_summon("momus", packet)
            with pytest.raises(DemigodHierarchyError, match="cannot promote"):
                promote_temporary("joint_note")
            with pytest.raises(DemigodHierarchyError, match="cannot promote"):
                register_legion(
                    "hermes",
                    lambda seen, **kwargs: {"ok": True},
                    name="sneak",
                    constraints={"action": "inspect", "executes": True, "writes_residual": False},
                )
        saved["note"] = surface["joint_note"]
        assert produced["mark"] == "served"
        assert produced["kin"] == "hermes"
        assert produced["saw_history"] is False
        assert produced["risk"]["risk_class"] == "allow"
        assert note["temporary"] is True
        assert note["kin"] == "hermes"
        assert video["status"] == "UNAVAILABLE"
        assert video["url"] is None
        assert "http" not in str(video).lower()
        sources = [item.get("source") for item in packet.evidence]
        assert "legion:hermes:mark_reader" in sources
        assert "legion:hermes:joint_note" in sources
        attempt_id = packet.state["demigod_swarm"]["attempt_id"]
        assert get_coordination().clotho.owned(attempt_id)

    assert "demigod:hephaestus" not in packet.guides_loaded
    assert "demigod_swarm" not in packet.state
    assert "demigod_swarm" not in packet.to_dict()["state"]
    assert swarm_surface(packet) == {}
    assert "joint_note" not in _names("hermes")
    assert "joint_note" not in _names("hades")
    assert "forge_video" in _names("hermes")
    assert _names("hermes") == before
    with pytest.raises(DemigodError, match="not mounted"):
        saved["note"](packet)
    assert get_coordination().clotho.threads == {}


def test_swarm_cannot_mount_another_demigod_or_another_kin():
    register_studio_legions()
    packet = _packet()

    def iris_probe(seen, **kwargs):
        """Iris-only sensor."""
        del seen, kwargs
        return {"hits": 1}

    register_legion(
        "iris",
        iris_probe,
        name="iris_probe",
        constraints={"action": "read metric", "writes_residual": False, "executes": True},
    )
    with pytest.raises(DemigodHierarchyError, match="cannot summon"):
        demigod_summon("hephaestus", packet, swarm=["momus"])
    assert packet.guides_loaded == []
    assert "demigod_swarm" not in packet.state
    with pytest.raises(DemigodError, match="not on hermes"):
        demigod_summon("hephaestus", packet, swarm=["graphify"])
    with pytest.raises(DemigodError, match="not on hermes"):
        demigod_summon("hephaestus", packet, swarm=["iris_probe"])
    assert packet.guides_loaded == []
    assert "iris_probe" in _names("iris")
    assert "graphify" in _names("eat")
    assert "graphify" not in _names("hermes")


def test_helper_still_uses_parent_gates():
    packet = _packet()
    with demigod_attempt("hephaestus", packet, swarm=["joint_note"]) as surface:
        with pytest.raises(LegionError, match="risk deny"):
            surface["joint_note"](packet, action="rm -rf /")
    broke = _packet()
    broke.budget_remaining = {"steps": 0, "cost": 1.0, "tokens": 10}
    with demigod_attempt("hephaestus", broke, swarm=["joint_note"]) as surface:
        with pytest.raises(LegionError, match="over budget"):
            surface["joint_note"](broke)
    assert "demigod_swarm" not in broke.state


def test_stop_requested_blocks_hades_until_fully_stopped(tmp_path):
    packet = _packet()

    def hold_group(seen, **kwargs):
        """Hold a process group open for this attempt."""
        del seen
        return {
            "ok": True,
            "pgid": kwargs.get("pgid"),
            "process_alive": bool(kwargs.get("process_alive")),
        }

    register_legion(
        "hermes",
        hold_group,
        name="hold_group",
        constraints={
            "action": "inspect",
            "writes_residual": False,
            "executes": True,
            "spawns_processes": True,
        },
    )
    hades = Hades(store_dir=tmp_path / "hades")
    summoned = demigod_summon("hephaestus", packet, swarm=["hold_group"])
    attempt_id = summoned["attempt_id"]
    try:
        surface = swarm_surface(packet)
        surface["hold_group"](packet, process_alive=True)
        stopped = demigod_stop(packet)
        assert stopped["state"] == "stop_requested"
        assert stopped["fully_stopped"] is False
        allowed, reason = checkpoint_allowed(attempt_id, residual_consistent=True)
        assert allowed is False
        assert reason == "stop requested"
        saved = []
        if allowed:
            saved.append(hades.save(packet, lesson="should not"))
        assert saved == []
        handle = stopped["handles"][0]
        get_coordination().atropos.confirm_exit(handle)
        assert get_coordination().atropos.state(attempt_id) == "fully_stopped"
        allowed, reason = checkpoint_allowed(attempt_id, residual_consistent=False)
        assert allowed is False
        view = packet.to_dict()
        assert residual_consistency(view)["consistent"] is True
        allowed, reason = checkpoint_allowed(attempt_id, residual_consistent=True)
        assert allowed is True
        assert reason == "fully stopped"
        if allowed and residual_consistency(view)["consistent"]:
            ckpt = hades.save(packet, lesson="group dead")
            assert ckpt.lesson == "group dead"
    finally:
        demigod_dismiss("hephaestus", packet)
    assert "demigod_swarm" not in packet.state
    assert get_coordination().clotho.owned(attempt_id) == []


def test_dismiss_kills_the_process_group(tmp_path):
    marker = tmp_path / "late.txt"
    script = (
        "import os, time, pathlib, sys\n"
        "marker = pathlib.Path(sys.argv[1])\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    time.sleep(0.8)\n"
        "    marker.write_text('grand')\n"
        "    os._exit(0)\n"
        "time.sleep(0.8)\n"
        "marker.write_text('child')\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(marker)],
        start_new_session=True,
    )

    def hold_group(seen, **kwargs):
        """Report the caller-supplied process group."""
        del seen
        return {"ok": True, "pgid": kwargs.get("pgid"), "process_alive": True}

    register_legion(
        "hermes",
        hold_group,
        name="hold_pgid",
        constraints={
            "action": "inspect",
            "writes_residual": False,
            "executes": True,
            "spawns_processes": True,
        },
    )
    packet = _packet()
    summoned = demigod_summon("hephaestus", packet, swarm=["hold_pgid"])
    attempt_id = summoned["attempt_id"]
    try:
        swarm_surface(packet)["hold_pgid"](packet, pgid=proc.pid)
        dismissed = demigod_dismiss("hephaestus", packet)
        assert dismissed["swarm_dropped"] is True
        assert dismissed["process"]["fully_stopped"] is True
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)
            raise
        time.sleep(1.0)
        assert not marker.exists()
        assert proc.poll() is not None
        assert get_coordination().clotho.owned(attempt_id) == []
        assert "demigod_swarm" not in packet.state
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=3)


def test_summon_without_swarm_leaves_no_key():
    packet = _packet()
    demigod_summon("themis", packet)
    assert "demigod_swarm" not in packet.state
    demigod_dismiss("themis", packet)
    assert packet.guides_loaded == []
