"""Clotho, Lachesis, Atropos, and Harmonia under Hermes."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.harness.tools import residual_consistency
from resileos.kin.hades import Hades
from resileos.harness.packet import ControlPacket
from resileos.kin.moirai import (
    HermesCoordination,
    checkpoint_allowed,
    reset_coordination,
)


@pytest.fixture(autouse=True)
def _fresh_desk():
    reset_coordination()
    yield
    reset_coordination()


def test_lachesis_cost_gate():
    desk = HermesCoordination()
    cheap = desk.lachesis.measure(expected_gain=0.2, budget_cost=0.5)
    assert cheap["expand"] is False
    wide = desk.lachesis.measure(expected_gain=0.9, budget_cost=0.4)
    assert wide["expand"] is True
    packet = {"id": "cycle-a", "subject": "Zeus"}
    desk.lachesis.note("a", packet, "abc")
    assert desk.lachesis.active["a"]["residual_hash"] == "abc"


def test_atropos_stop_versus_fully_stopped():
    desk = HermesCoordination()
    desk.clotho.spin("turn", handle_id="child", cancel=lambda: None, manual_exit=True)
    desk.clotho.spin(
        "turn",
        handle_id="grand",
        parent_id="child",
        cancel=lambda: None,
        manual_exit=True,
    )
    cut = desk.atropos.cut("turn")
    assert cut["state"] == "stop_requested"
    assert cut["fully_stopped"] is False
    assert desk.atropos.state("turn") == "stop_requested"
    desk.atropos.confirm_exit("child")
    assert desk.atropos.state("turn") == "stop_requested"
    desk.atropos.confirm_exit("grand")
    assert desk.atropos.state("turn") == "fully_stopped"


def test_grandchild_callback_does_not_write_late(tmp_path):
    marker = tmp_path / "late.txt"
    pending: list = []
    pending.append(lambda: marker.write_text("late"))

    def cancel_child():
        return None

    def cancel_grandchild():
        pending.clear()

    desk = HermesCoordination()
    desk.clotho.spin("turn", handle_id="child", cancel=cancel_child)
    desk.clotho.spin("turn", handle_id="grand", parent_id="child", cancel=cancel_grandchild)
    desk.atropos.cut("turn")
    for job in list(pending):
        job()
    assert not marker.exists()
    assert desk.atropos.state("turn") == "fully_stopped"


def test_grandchild_process_group_does_not_write_late(tmp_path):
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
    desk = HermesCoordination()
    desk.clotho.spin("turn", handle_id="child", pgid=proc.pid)
    desk.atropos.cut("turn")
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=3)
        raise
    time.sleep(1.0)
    assert not marker.exists()
    assert desk.atropos.state("turn") == "fully_stopped"


def test_hades_waits_for_fully_stopped_and_consistency(tmp_path):
    desk = HermesCoordination()
    from resileos.kin import moirai as moirai_mod

    moirai_mod._DESK = desk
    hades = Hades(store_dir=tmp_path / "hades")
    packet = ControlPacket(id="turn")
    packet.verified = True
    desk.clotho.spin("turn", handle_id="child", cancel=lambda: None, manual_exit=True)
    desk.atropos.cut("turn")
    allowed, reason = checkpoint_allowed("turn", residual_consistent=True)
    assert allowed is False
    assert reason == "stop requested"
    desk.atropos.confirm_exit("child")
    allowed, _reason = checkpoint_allowed("turn", residual_consistent=False)
    assert allowed is False
    allowed, reason = checkpoint_allowed("turn", residual_consistent=True)
    assert allowed is True
    assert reason == "fully stopped"
    view = packet.to_dict()
    assert residual_consistency(view)["consistent"] is True
    if allowed and residual_consistency(view)["consistent"]:
        ckpt = hades.save(packet, lesson="group dead")
        assert ckpt.lesson == "group dead"


def test_harmonia_shares_similar_hashes_and_not_dissimilar():
    desk = HermesCoordination()
    packet_a = {"id": "1", "subject": "Zeus", "relation": "domain"}
    same = "aaaaaaaaaa"
    near = "aaaaaaaabb"
    other = "bbbbbbbbbb"
    first = desk.harmonia.route("a", same, packet_a)
    assert first["path"] == "independent"
    shared = desk.harmonia.route("b", near, {"id": "2", "subject": "Hera", "relation": "seat"})
    assert shared["path"] == "shared"
    assert shared["shared_with"] == "a"
    alone = desk.harmonia.route(
        "c",
        other,
        {"id": "9", "subject": "Hera", "relation": "seat"},
    )
    assert alone["path"] == "independent"

    packet = {
        "verified": True,
        "scars": [],
        "evidence": [{"source": "probe", "result": {"matched": 1}}],
    }
    refused = desk.harmonia.certify(
        residual_consistent=False,
        apollo_result={"success": True},
        packet=packet,
    )
    assert refused["accepted"] is False
    assert refused["certified_leaf"] is False
    kept = desk.harmonia.certify(
        residual_consistent=True,
        apollo_result={"success": True},
        packet=packet,
    )
    assert kept["accepted"] is True
    assert kept["verify_on_stop"]["verified"] is True
