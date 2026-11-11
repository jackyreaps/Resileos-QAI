"""Aphrodite state, legions, routes, and verified-only fragments."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from resileos.harness.packet import ControlPacket
from resileos.kin.aphrodite import (
    AphroditeState,
    AphroditeStore,
    get_store,
    make_aphrodite_handler,
    record_preference,
    register_aphrodite_legions,
    set_store,
)
from resileos.kin.bundle import build_kin_bundle
from resileos.kin.hades import Hades
from resileos.kin.legions import invoke_legion, reset_legions


@pytest.fixture
def store(tmp_path):
    held = AphroditeStore(tmp_path / "aphrodite")
    set_store(held)
    yield held
    set_store(None)


@pytest.fixture
def legions():
    reset_legions()
    register_aphrodite_legions()
    yield
    reset_legions()
    app = sys.modules.get("app")
    if app is not None:
        app._register_runtime_legions()


def test_preference_does_not_write_residual_facts(store):
    learned = []
    state, fragment = record_preference("anon", "tea", like=True)
    state.handle("tea is a fact", verified=False)
    assert fragment
    assert "tea" in state.preferences
    assert state.to_dict()["writes_residual"] is False
    assert learned == []
    assert "subject" not in state.to_dict()


def test_unverified_step_does_not_grow(store):
    state = store.get("anon")
    assert state.advance("teach_fact", verified=False) is None
    assert state.persona["growth_stage"] == 0
    fragment = state.advance("teach_fact", verified=True)
    assert fragment
    assert state.persona["growth_stage"] == 1
    assert state.advance("teach_fact", verified=True) is None
    assert state.persona["growth_stage"] == 1


def test_signals_default_neutral(store):
    state = AphroditeState()
    before = state.rapport
    state.fold_signals(None)
    assert state.rapport == before
    state.fold_signals({})
    assert state.rapport == pytest.approx(0.5)
    state.fold_signals({"oxtr": 1.0})
    assert state.rapport != before


def test_calliope_ligeia_echo(store, legions, tmp_path):
    record_preference("anon", "tea", like=True, care=5)
    draft = invoke_legion(
        "aphrodite",
        "calliope",
        {"budget_remaining": {"steps": 3, "cost": 1}},
        hub_id="anon",
        residual_hash="abc123",
    )
    assert draft["verified"] is False
    assert draft["writes_residual"] is False
    assert draft["evidence"] == "abc123"
    assert "tea" in draft["preferences"]
    assert "history" not in draft

    cue = invoke_legion(
        "aphrodite",
        "ligeia",
        {"budget_remaining": {"steps": 3, "cost": 1}},
        hub_id="anon",
        topic="tea",
    )
    assert cue["suggestion_only"] is True
    assert cue["attention_cue"] == "high-care:tea"
    assert cue["verified"] is False

    hades = Hades(store_dir=tmp_path / "hades")
    probed = invoke_legion(
        "aphrodite",
        "echo",
        {"budget_remaining": {"steps": 3, "cost": 1}},
        probe="tea",
        save_lesson=True,
        hades=hades,
    )
    assert probed["lesson_only"] is True
    assert probed["lesson"].startswith("habit-check:")
    assert probed["writes_residual"] is False
    saved = hades.load(probed["checkpoint"])
    assert saved is not None
    assert saved.lesson == probed["lesson"]
    assert saved.extra == {}


def test_fragment_only_on_verified_cycle(store, tmp_path):
    state = store.get("hub1")
    closed_bundle = build_kin_bundle()
    closed_bundle._hades = Hades(store_dir=tmp_path / "closed")
    _report, _policy, closed = closed_bundle.cycle(aphrodite_state=state)
    assert closed["verified"] is False
    assert "tutorial_fragment" not in closed
    assert state.persona["growth_stage"] == 0

    bundle = build_kin_bundle()
    bundle._hades = Hades(store_dir=tmp_path / "hades")
    residual = type("Stub", (), {"packet_hash": "abc123", "topics": []})()
    _report, _policy, harness = bundle.cycle(
        aphrodite_state=state,
        residual_packet=residual,
    )
    assert harness["verified"] is True
    assert harness["tutorial_fragment"]
    ckpt = bundle._hades.load(harness["checkpoint"])
    assert ckpt.extra["aphrodite"]["persona"]["growth_stage"] == 1

    strict = build_kin_bundle()
    strict._hades = Hades(store_dir=tmp_path / "strict")
    state.update_preference("tea", like=True, care=5)
    cared = type("Stub", (), {"packet_hash": None, "topics": ["tea"]})()
    _report, _policy, blocked = strict.cycle(aphrodite_state=state, residual_packet=cared)
    assert blocked["verified"] is False
    assert "high-care" in blocked["consistency"]["reason"]
    assert "tutorial_fragment" not in blocked

    hidden = state.handle("a fact", verified=False)
    assert hidden["tutorial_fragment"] is None
    shown = state.handle("a fact", verified=True)
    assert shown["tutorial_fragment"]


def test_handler_declines_facts():
    handler = make_aphrodite_handler()
    out = handler("Zeus domain sky", residual_hash="hh", verified=False)
    assert out["declined"] is True
    assert out["writes_residual"] is False
    assert out["tutorial_fragment"] is None


def test_chat_like_and_routes(store, monkeypatch):
    from resileos.chat.router import dispatch

    class Titan:
        entities = {}
        relations = {}
        facts = []

        def learn(self, *args):
            raise AssertionError("preference must not learn")

        def ask_list(self, *_args):
            return []

    reply, status, action = dispatch("I like quiet", Titan(), "anon")
    assert status == "ACCEPTED"
    assert "quiet" in reply
    assert action["wrote"] is False
    assert action.get("tutorial_fragment")
    reply2, _status2, action2 = dispatch("I don't like noise", Titan(), "anon")
    assert "noise" in reply2
    assert action2.get("tutorial_fragment") is None
    held = get_store().get("anon")
    assert held.preferences["quiet"]["likes"] == 1
    assert held.preferences["noise"]["dislikes"] == 1

    monkeypatch.setattr("app._AUTH_BYPASS", True)
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    got = client.get("/api/v1/aphrodite/anon/state")
    assert got.status_code == 200
    assert got.json()["preferences"]["quiet"]["likes"] == 1
    posted = client.post(
        "/api/v1/aphrodite/anon/preference",
        json={"topic": "tea", "like": True, "care": 2},
    )
    assert posted.status_code == 200
    assert posted.json()["preferences"]["tea"]["care"] == 2
    reset = client.post("/api/v1/aphrodite/anon/reset")
    assert reset.status_code == 200
    assert reset.json()["preferences"] == {}
    assert reset.json()["persona"]["growth_stage"] == 0


def test_hades_extra_roundtrip(tmp_path):
    hades = Hades(store_dir=tmp_path / "hades")
    packet = ControlPacket(id="aph")
    packet.verified = True
    state = AphroditeState()
    state.advance("run_tool", verified=True)
    ckpt = hades.save(packet, lesson="lesson", extra={"aphrodite": state.to_dict()})
    hades._cache.clear()
    loaded = hades.load(ckpt.id)
    assert loaded.extra["aphrodite"]["completed"] == ["run_tool"]
    assert loaded.lesson == "lesson"
