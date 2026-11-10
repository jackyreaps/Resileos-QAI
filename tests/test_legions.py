"""Legions stay inside one Kin."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.harness.packet import ControlPacket
from resileos.kin.hades import Hades
from resileos.kin.legions import (
    LegionError,
    invoke_legion,
    kin_catalogue,
    register_example_legions,
    register_legion,
    reset_legions,
)


@pytest.fixture(autouse=True)
def _clean_legions():
    reset_legions()
    yield
    reset_legions()


def _packet(**overrides):
    packet = {
        "id": "legion",
        "budget_remaining": {"steps": 5, "cost": 1.0, "tokens": 100},
        "evidence": [],
        "history": [{"event": "secret-history"}],
        "scars": [],
        "verified": False,
        "lesson": "the lesson",
        "artefact": {"status": "ok"},
    }
    packet.update(overrides)
    return packet


def test_examples_are_off_by_default():
    assert register_example_legions() == []
    assert kin_catalogue("iris") == []
    assert kin_catalogue("hades") == []
    assert kin_catalogue("hermes") == []


def test_cross_kin_call_is_refused():
    def sensor(seen, **kwargs):
        """Read a metric."""
        return {"hits": 1}

    register_legion(
        "iris",
        sensor,
        name="sensor",
        constraints={"action": "read metric", "writes_residual": False, "executes": True},
    )
    assert [row["name"] for row in kin_catalogue("iris")] == ["sensor"]
    assert kin_catalogue("metis") == []
    with pytest.raises(LegionError, match="cross-kin"):
        invoke_legion("metis", "sensor", _packet())


def test_metis_legion_cannot_execute():
    def policy(seen, **kwargs):
        """Propose a disable list."""
        return {"disable_children": ["mouth"], "allow_mouth": True}

    with pytest.raises(LegionError, match="cannot execute"):
        register_legion(
            "metis",
            policy,
            name="router",
            constraints={"executes": True, "writes_residual": False},
        )
    register_legion(
        "metis",
        policy,
        name="router",
        constraints={"action": "classify", "executes": False, "writes_residual": False},
    )
    learned = []
    with pytest.raises(LegionError, match="cannot execute"):
        invoke_legion(
            "metis",
            "router",
            _packet(),
            execute=True,
            learn_fn=lambda s, r, o: learned.append((s, r, o)),
        )
    out = invoke_legion("metis", "router", _packet())
    assert out["executed"] is False
    assert out["verified"] is False
    assert "allow_mouth" not in out["policy"]
    assert learned == []


def test_iris_legion_cannot_write_residual_state():
    def reader(seen, **kwargs):
        """Read logs."""
        return {"lines": 0, "verified": True}

    with pytest.raises(LegionError, match="cannot write residual"):
        register_legion(
            "iris",
            reader,
            name="reader",
            constraints={"writes_residual": True, "executes": True},
        )
    register_legion(
        "iris",
        reader,
        name="reader",
        constraints={"action": "read logs", "writes_residual": False, "executes": True},
    )
    packet = _packet()
    with pytest.raises(LegionError, match="cannot write residual"):
        invoke_legion("iris", "reader", packet, write_residual=True)
    out = invoke_legion("iris", "reader", packet)
    assert out["verified"] is False
    assert packet["verified"] is False
    assert packet["evidence"][-1]["source"] == "legion:iris:reader"


def test_over_budget_call_is_refused():
    calls = []

    def nav(seen, **kwargs):
        calls.append(seen)
        return {"ok": True}

    register_legion(
        "hermes",
        nav,
        name="nav",
        constraints={"action": "navigate", "executes": True, "writes_residual": False},
    )
    with pytest.raises(LegionError, match="over budget"):
        invoke_legion(
            "hermes",
            "nav",
            _packet(budget_remaining={"steps": 0, "cost": 1.0}),
        )
    assert calls == []


def test_hermes_sees_artefact_and_lesson_not_history():
    seen_packets = []

    def reviewer(seen, **kwargs):
        seen_packets.append(seen)
        return {"defects": []}

    register_legion(
        "hermes",
        reviewer,
        name="blind",
        constraints={"action": "review", "executes": True, "writes_residual": False},
    )
    out = invoke_legion("hermes", "blind", _packet())
    assert "history" not in seen_packets[0]
    assert seen_packets[0]["lesson"] == "the lesson"
    assert seen_packets[0]["artefact"] == {"status": "ok"}
    assert out["verified"] is False


def test_hades_restore_drops_history_and_scars(tmp_path):
    register_example_legions(enable=True, lesson_path=str(tmp_path / "lessons.txt"))
    store = Hades(store_dir=tmp_path / "hades")
    original = ControlPacket(id="attempt")
    original.scars = ["open-scar"]
    original.append({"event": "secret-history", "n": 1})
    original.verified = True
    checkpoint = store.save(original, lesson="keep the lesson")
    out = invoke_legion(
        "hades",
        "restore_fresh",
        _packet(),
        hades=store,
        checkpoint_id=checkpoint.id,
    )
    events = [item.get("event") for item in out["history"]]
    assert "secret-history" not in events
    assert out["scars"] == []
    assert out["verified"] is False
    assert out["lesson"] == "keep the lesson"


def test_nothing_marks_verified_without_apollo():
    def marker(seen, **kwargs):
        return {"verified": True, "status": "ok"}

    register_legion(
        "hermes",
        marker,
        name="marker",
        constraints={"action": "inspect", "executes": True, "writes_residual": False},
    )
    packet = _packet()
    hermes = invoke_legion("hermes", "marker", packet)
    assert hermes["verified"] is False
    assert packet["verified"] is False

    register_legion(
        "apollo",
        marker,
        name="marker",
        constraints={
            "action": "inspect",
            "executes": True,
            "writes_residual": False,
            "may_set_verified": True,
        },
    )
    denied = invoke_legion("apollo", "marker", _packet(), apollo_result={"success": False})
    assert denied["verified"] is False
    clean = _packet()
    allowed = invoke_legion(
        "apollo",
        "marker",
        clean,
        apollo_result={"success": True},
    )
    assert allowed["verified"] is True
    assert clean["verified"] is True
    assert allowed["verify_on_stop"]["verified"] is True


def test_eat_learn_is_gated_and_a_deny_does_not_write():
    def ingest(seen, **kwargs):
        return {"claims": [("Zeus", "domain", "sky")]}

    register_legion(
        "eat",
        ingest,
        name="ingest",
        constraints={"action": "ingest", "writes_residual": True, "executes": True},
    )
    learned = []
    with pytest.raises(LegionError, match="risk deny"):
        invoke_legion(
            "eat",
            "ingest",
            _packet(),
            action="delete the store",
            learn_fn=lambda s, r, o: learned.append((s, r, o)),
        )
    assert learned == []
    invoke_legion(
        "eat",
        "ingest",
        _packet(),
        action="ingest row",
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
    )
    assert learned == [("Zeus", "domain", "sky")]


def test_example_legions_stay_local(tmp_path):
    calls = []

    def inference(prompt):
        calls.append(prompt)
        return "local"

    register_example_legions(
        enable=True,
        inference_fn=inference,
        trace_path=str(tmp_path / "trace.jsonl"),
        lesson_path=str(tmp_path / "lessons.txt"),
    )
    with pytest.raises(LegionError, match="escalate"):
        invoke_legion("hermes", "ollama_local", _packet(), probability=0.99, prompt="hi")
    assert calls == []
    out = invoke_legion("hermes", "ollama_local", _packet(), probability=0.4, prompt="hi")
    assert out["text"] == "local"
    assert out["network"] is False
    assert calls == ["hi"]

    invoke_legion(
        "hades",
        "jsonl_trace",
        _packet(),
        record={"event": "probe", "n": 1},
    )
    read = invoke_legion("iris", "jsonl_trace", _packet())
    assert read["lines"] == [{"event": "probe", "n": 1}]
    assert read["wrote"] is False

    notes = invoke_legion("hades", "lesson_notes", _packet(), note="one line")
    assert notes["vector_store"] is False
    assert (tmp_path / "lessons.txt").read_text(encoding="utf-8") == "one line\n"

    with pytest.raises(LegionError, match="risk deny"):
        invoke_legion("apollo", "action_placeholder", _packet(), action="rm -rf /")
    placeholder = invoke_legion("hermes", "action_placeholder", _packet(), action="inspect")
    assert placeholder["executed_code"] is False
    assert placeholder["saw_history"] is False
    assert placeholder["verified"] is False


def test_legion_cannot_bypass_core_zeus_hades_or_mouth():
    def tool(seen, **kwargs):
        return {"ok": True}

    register_legion(
        "apollo",
        tool,
        name="gate",
        constraints={"action": "inspect", "executes": True, "may_set_verified": True},
    )
    packet = _packet()
    with pytest.raises(LegionError, match="residual core"):
        invoke_legion("apollo", "gate", packet, residual_core=object())
    with pytest.raises(LegionError, match="Zeus"):
        invoke_legion("apollo", "gate", packet, bypass_zeus=True)
    with pytest.raises(LegionError, match="Hades"):
        invoke_legion("apollo", "gate", packet, bypass_hades=True)
    with pytest.raises(LegionError, match="mouth"):
        invoke_legion("apollo", "gate", packet, force_mouth=True)


def test_jsonl_trace_is_not_a_global_tool():
    register_example_legions(enable=True, trace_path="unused.jsonl", lesson_path="unused.txt")
    names = {row["name"] for row in kin_catalogue("iris")}
    assert "jsonl_trace" in names
    assert "ollama_local" not in names
    dumped = json.dumps(kin_catalogue("iris"))
    assert "metis" not in dumped
