"""Candidate answers, fast chat, deferred review, budget, Morpheus, Dionysus."""
from __future__ import annotations

import asyncio
import threading
import time

import numpy as np

from resileos.chat.deferred_review import deliver
from resileos.harness.packet import ControlPacket
from resileos.harness.separated import Proposal, Verdict, zeus_head
from resileos.kin.demigods.checks import hephaestus_check
from resileos.kin.demigods.morpheus import compress, replay, run_idle
from resileos.kin.dionysus import expand, register_dionysus, reset_hub, retrieve
from resileos.kin.hermes import HEPHAESTUS_MAX_DEPTH, HEPHAESTUS_MAX_ITEMS, HermesBudget
from resileos.kin.iris import classify_intent
from resileos.kin.legions import kin_catalogue
from resileos.kin.metis import clip_hops, hermes_budget_for
from resileos.latent_hub import LatentHub
from resileos.ui.custom_mouth import answer, phrase_candidate
from resileos.ui.language_codex import speak


def _titan():
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from titanos import Titanos, TitanosConfig

    titan = Titanos(TitanosConfig(dim=256, m=16, n=16, r=4, n_loops=2, seed=1))
    return titan


def test_exact_recall_and_unknown_entity_stay_put():
    titan = _titan()
    titan.learn("Zeus", "domain", "sky")
    exact = titan.ask("Zeus", "domain")
    assert exact.status == "ACCEPTED"
    assert exact.value == "sky"
    assert exact.candidate is None

    unknown = titan.ask("Odin", "domain")
    assert unknown.status == "ABSTAINED"
    assert unknown.value is None
    assert unknown.candidate is None
    assert "unknown entity" in unknown.reason

    missing_relation = titan.ask("Zeus", "capital_of")
    assert missing_relation.status == "ABSTAINED"
    assert missing_relation.value is None

    before = titan.stats()["facts"]
    titan.ask("Zeus", "domain")
    assert titan.stats()["facts"] == before


def test_empty_slot_stays_abstained_and_partial_chain_is_candidate():
    titan = _titan()
    titan.learn("alice", "parent_of", "bob")
    titan.learn("bob", "parent_of", "carol")
    empty = titan.ask("carol", "parent_of")
    assert empty.status == "ABSTAINED"
    assert empty.value is None
    assert titan.ask_list("carol", "parent_of") == []

    partial = titan.chain("alice", ["parent_of", "capital_of"])
    assert partial.status == "CANDIDATE"
    assert partial.value is None
    assert partial.unverified is True
    assert partial.candidate == "bob"
    assert any(item["signal"] == "partial_chain_hop" for item in partial.evidence)
    assert "unverified" in partial.reason
    assert titan.stats()["facts"] == 2


def test_candidate_nearest_neighbour_is_not_stored():
    titan = _titan()
    titan.learn("zeus", "child", "ares")
    titan.learn("zeus", "child", "athena")
    before = len(titan.facts)

    def _miss(*_args, **_kwargs):
        return "nobody", 0.2

    titan._cleanup = _miss
    answer_row = titan.ask("zeus", "child")
    assert answer_row.status == "CANDIDATE"
    assert answer_row.value is None
    assert answer_row.unverified is True
    assert answer_row.candidate in {"ares", "athena"}
    assert answer_row.evidence
    assert len(titan.facts) == before
    spoken = phrase_candidate(answer_row.candidate, answer_row.evidence)
    assert spoken == (
        f"I don't have that on record; closest match is {answer_row.candidate}, unverified."
    )


def test_conflict_mouth_explains_windows_without_a_model():
    rows = [
        {
            "subject": "Athens",
            "relation": "capital_of",
            "obj": "Ottoman",
            "valid_from": "1458-01-01",
            "valid_to": "1834-01-01",
        },
        {
            "subject": "Athens",
            "relation": "capital_of",
            "obj": "Greece",
            "valid_from": "1834-01-01",
            "valid_to": None,
        },
    ]
    called = []

    def _model(prompt: str) -> str:
        called.append(prompt)
        return "MODEL"

    out = answer(rows, "capital", status="CONFLICT", model_fn=_model)
    assert called == []
    assert out["backend"] == "structured"
    assert out["epistemic"] == "CONFLICT"
    assert "Ottoman" in out["text"]
    assert "Greece" in out["text"]
    assert "1458-01-01" in out["text"]
    assert "1834-01-01" in out["text"]
    assert out["text"].strip() != "CONFLICT"
    spoken = speak(rows, status="CONFLICT")
    assert "These records disagree" in spoken["text"]
    assert "Ottoman" in spoken["text"]
    assert spoken["epistemic"] == "CONFLICT"

    empty = answer([], "salary")
    assert empty["epistemic"] == "ABSTAINED"
    assert "No stored" in empty["text"]


def test_fast_path_skips_the_cycle_and_does_not_reuse_one_line():
    from resileos.answer.agent_loop import run_agent_chat

    class Store:
        entities: dict = {}
        relations: dict = {}

        def ask_list(self, *_args, **_kwargs):
            raise AssertionError("fast path asked the store")

        def learn(self, *_args, **_kwargs):
            raise AssertionError("fast path learned")

    calls = []

    def _cycle(*_args, **_kwargs):
        calls.append("cycle")
        return {"verified": True}

    import resileos.chat.turn_cycle as turn_cycle

    original = turn_cycle.run_bounded_cycle
    turn_cycle.run_bounded_cycle = _cycle
    class Quiet(Store):
        def ask_list(self, *_args, **_kwargs):
            return []

    try:
        hello = asyncio.run(run_agent_chat(Store(), "hello", hub_id="fast1", persona="honest"))
        thanks = asyncio.run(run_agent_chat(Store(), "thanks", hub_id="fast1", persona="honest"))
        meta = asyncio.run(run_agent_chat(Store(), "who are you", hub_id="fast1"))
        assert calls == []
        forced = asyncio.run(
            run_agent_chat(
                Quiet(),
                "hello",
                hub_id="fast1",
                force_class="HUB_LEARN",
            )
        )
    finally:
        turn_cycle.run_bounded_cycle = original
    assert hello["verified"] is False
    assert hello["source"] == "conversational"
    assert hello["evidence"] == []
    assert hello["checks_skipped"] == ["themis", "momus", "atlas"]
    assert "I am online and ready" not in hello["reply_text"]
    assert hello["reply_text"] != thanks["reply_text"]
    assert hello["reply_text"] != meta["reply_text"]
    assert "sky" not in hello["reply_text"]
    assert calls == ["cycle"]
    assert forced["cycle_verified"] is True
    fact = classify_intent("what is the domain of Zeus", titanos=Store())
    assert fact == "factual"
    assert classify_intent("remember that I prefer tea") == "mutate"
    assert classify_intent("/tool residual_consistency") == "tool"


def test_reply_returns_before_a_failing_review_commits():
    learned = []
    started = threading.Event()
    release = threading.Event()

    def review():
        started.set()
        release.wait(timeout=2)
        packet = ControlPacket(id="defer-fail")
        proposal = Proposal(
            id=packet.id,
            writer="mouth",
            action_type="learn",
            result={"status": "no"},
            claims=[("ada", "domain", "sky")],
            packet=packet,
        )

        def reject(item):
            return Verdict(item.id, "review", False, "no", [])

        return zeus_head(
            proposal,
            [("review", reject)],
            lambda subject, relation, obj: learned.append((subject, relation, obj)),
        )

    reply, handle = deliver(
        {"text": "I don't have that on record; closest match is sky, unverified."},
        review,
    )
    assert reply["text"].startswith("I don't have that on record")
    assert started.wait(timeout=1)
    assert handle.done() is False
    release.set()
    assert handle.wait(timeout=2)
    assert learned == []
    assert handle.result["applied"] is False


def test_dynamic_budget_stays_inside_hephaestus_caps():
    simple = hermes_budget_for("what is the domain of zeus")
    multi = hermes_budget_for("who is the parent of the parent of zeus")
    assert simple.max_depth < multi.max_depth
    assert simple.max_items < multi.max_items
    assert multi.max_depth <= HEPHAESTUS_MAX_DEPTH
    assert multi.max_items <= HEPHAESTUS_MAX_ITEMS
    assert clip_hops(["parent_of", "parent_of", "domain"], simple) == ["parent_of"]
    assert clip_hops(["parent_of", "parent_of"], multi) == ["parent_of", "parent_of"]

    packet = ControlPacket(id="cap")
    packet.evidence = [{"source": "probe", "result": {"matched": 1}}]
    over = hephaestus_check(
        packet,
        hermes_budget=HermesBudget(max_depth=HEPHAESTUS_MAX_DEPTH + 1, max_items=4, used=0),
    )
    assert over.verified is False
    assert "hermes" in over.reason


def test_morpheus_promotes_only_through_zeus():
    learned = []

    def learn(subject, relation, obj):
        learned.append((subject, relation, obj))

    candidate_turns = [
        {"subject": "ada", "relation": "domain", "obj": "sky", "status": "CANDIDATE"},
        {"subject": "ada", "relation": "domain", "obj": "sky", "status": "CANDIDATE"},
    ]
    held = run_idle(candidate_turns, learn)
    assert held["results"]
    assert learned == []
    assert held["results"][0]["applied"] is False
    assert held["results"][0]["backend"] == "studio-codec"

    verified_turns = [
        {"subject": "ada", "relation": "domain", "obj": "sky", "status": "ACCEPTED"},
        {"subject": "ada", "relation": "domain", "obj": "sky", "status": "ACCEPTED"},
    ]
    promoted = run_idle(verified_turns, learn)
    assert promoted["results"][0]["applied"] is True
    assert learned == [("ada", "domain", "sky")]

    seen = []

    def backend(matrix):
        seen.append(np.asarray(matrix).shape)
        return {"hook": True}

    hooked = compress(replay(verified_turns)[0], backend=backend)
    assert seen == [(8, 8)]
    assert hooked["backend"] == "hook"

    scarred = run_idle(
        [
            {"subject": "ada", "relation": "likes", "obj": "tea", "status": "ACCEPTED", "scars": ["open"]},
            {"subject": "ada", "relation": "likes", "obj": "tea", "status": "ACCEPTED", "scars": ["open"]},
        ],
        learn,
    )
    assert scarred["results"][0]["applied"] is False
    assert learned == [("ada", "domain", "sky")]


def test_dionysus_expands_into_the_latent_hub_and_not_titanos():
    hub = reset_hub()
    learned = []

    class Titan:
        def learn(self, *_args):
            learned.append(_args)

    out = expand("pere works", hub)
    assert "father" in out["neighbours"]
    assert out["writes_titanos"] is False
    assert out["learned"] is False
    assert learned == []
    assert hub.get("pere works") is not None
    Titan().learn("should", "not", "run")
    assert learned == [("should", "not", "run")]
    learned.clear()

    register_dionysus()
    names = {row["name"] for row in kin_catalogue("hermes")}
    assert "dionysus" in names
    assert "dionysus" not in {row["name"] for row in kin_catalogue("iris")}

    contexts = [
        {"subject": "ada", "relation": "parent", "obj": "bea"},
        {"subject": "ada", "relation": "likes", "obj": "tea"},
    ]
    ranked = retrieve("father", contexts, HermesBudget(max_depth=2, max_items=2), hub)
    assert ranked[0]["relation"] == "parent"
    assert learned == []


def test_latent_hub_is_not_the_fact_store():
    hub = LatentHub(dim=32, seed=3)
    vector = hub.encode("parent")
    hub.put("parent", vector)
    nearest = hub.nearest(vector, k=1)
    assert nearest[0]["key"] == "parent"
    assert "facts" not in hub.__dict__
    other = hub.encode("parent")
    assert np.array_equal(vector, other)


def test_budget_clip_changes_chain_work():
    """Tight depth stops after one hop. Wide depth keeps both. This is the latency lever."""
    titan = _titan()
    titan.learn("a", "parent_of", "b")
    titan.learn("b", "works_at", "acme")
    relations = ["parent_of", "works_at"]
    tight = hermes_budget_for("what is the parent_of of a")
    wide = hermes_budget_for("who is the parent of the parent of a")

    def timed(budget):
        hops = clip_hops(relations, budget)
        started = time.perf_counter()
        answer_row = titan.chain("a", hops)
        elapsed = (time.perf_counter() - started) * 1000
        return hops, answer_row, elapsed

    tight_hops, tight_answer, tight_ms = timed(tight)
    wide_hops, wide_answer, wide_ms = timed(wide)
    assert tight_hops == ["parent_of"]
    assert wide_hops == ["parent_of", "works_at"]
    assert tight_answer.value == "b"
    assert wide_answer.value == "acme"
    assert tight_ms >= 0 and wide_ms >= 0
