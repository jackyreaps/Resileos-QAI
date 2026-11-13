"""Demi-god skill layer: summon, checks, hierarchy, blind cycle."""
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from importlib.resources import files

import resileos.harness.tools as harness_tools
from resileos.capacity import hopfield_cap
from resileos.harness.packet import ControlPacket
from resileos.harness.separated import maker_blind_verifier_cycle
from resileos.harness.surface import (
    ALWAYS_VISIBLE_TOOLS,
    DEMIGOD_TOOLS,
    always_visible_schemas,
    search_tool_surface,
)
from resileos.harness.tools import GUIDE_BODY_CAP, guide_load
from resileos.kin.demigods import (
    MAX_NEED_MORE_ROUNDS,
    OUTCOME_NEED_MORE,
    DemigodError,
    DemigodHierarchyError,
    active_demigod,
    atlas_check,
    demigod_dismiss,
    demigod_duty,
    demigod_search,
    demigod_summon,
    durable_cross_attempt,
    hephaestus_check,
    list_demigods,
    momus_review,
    nike_check,
    refuse_learn,
    refuse_residual_ownership,
    router,
    themis_check,
)
from resileos.kin.hades import Hades
from resileos.kin.hermes import HermesBudget

HASH = "ab" * 32
OTHER_HASH = "cd" * 32


def _answer_tools():
    """Load the answer tool catalog without importing answer backends."""
    path = (
        Path(__file__).resolve().parents[1]
        / "src/resileos/answer/tools_schema.py"
    )
    spec = importlib.util.spec_from_file_location(
        "resileos_answer_tools_schema", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _packet(**overrides) -> ControlPacket:
    pkt = ControlPacket(id="duty")
    pkt.evidence = [{"source": "probe", "result": {"matched": 2, "passed": 2}}]
    pkt.verified = True
    for key, value in overrides.items():
        setattr(pkt, key, value)
    return pkt


# ── summon / dismiss ────────────────────────────────────────────────


def test_summon_then_dismiss_on_control_packet():
    packet = ControlPacket(id="p")
    summoned = demigod_summon("themis", packet)
    assert summoned["summoned"] is True
    assert "demigod:themis" in packet.guides_loaded
    body = packet.guide_bodies["demigod:themis"]
    assert body.startswith("# Themis")
    assert "Hades lesson" in body
    assert len(body) <= GUIDE_BODY_CAP
    dismissed = demigod_dismiss("themis", packet)
    assert dismissed["dismissed"] is True
    assert "demigod:themis" not in packet.guides_loaded
    assert "demigod:themis" not in packet.guide_bodies


def test_summon_then_dismiss_on_callers_dict():
    kept: dict = {}
    demigod_summon("momus", kept)
    assert kept["guides_loaded"] == ["demigod:momus"]
    assert "Momus" in kept["guide_bodies"]["demigod:momus"]
    demigod_dismiss("momus", kept)
    assert kept["guides_loaded"] == []
    assert "demigod:momus" not in kept["guide_bodies"]


def test_summon_then_dismiss_through_to_dict_updates_packet():
    packet = ControlPacket(id="p")
    demigod_summon("nike", packet.to_dict())
    assert "demigod:nike" in packet.guides_loaded
    assert packet.guide_bodies["demigod:nike"].startswith("# Nike")
    demigod_dismiss("nike", packet.to_dict())
    assert "demigod:nike" not in packet.guides_loaded
    assert "demigod:nike" not in packet.guide_bodies


def test_dismiss_matches_exact_id_not_substring():
    packet = ControlPacket(id="p")
    packet.guides_loaded = [
        "demigod:themis",
        "demigod:themis-extra",
        "demigod:antithemis",
        "docs/themis.md",
        "themis",
    ]
    packet.guide_bodies = {
        "demigod:themis": "drop",
        "demigod:themis-extra": "stay",
        "docs/themis.md": "stay-doc",
    }
    demigod_dismiss("themis", packet)
    assert packet.guides_loaded == [
        "demigod:themis-extra",
        "demigod:antithemis",
        "docs/themis.md",
        "themis",
    ]
    assert "demigod:themis" not in packet.guide_bodies
    assert packet.guide_bodies["demigod:themis-extra"] == "stay"
    assert packet.guide_bodies["docs/themis.md"] == "stay-doc"


def test_guide_body_is_capped(monkeypatch):
    monkeypatch.setattr(harness_tools, "GUIDE_BODY_CAP", 32)
    packet = ControlPacket(id="p")
    demigod_summon("themis", packet)
    assert len(packet.guide_bodies["demigod:themis"]) == 32


def test_guide_load_still_records_names_and_caps_bodies():
    packet = ControlPacket(id="g")
    guide_load(["docs/harness/AGENTS.md"], packet.to_dict())
    assert packet.guides_loaded == ["docs/harness/AGENTS.md"]
    guide_load(["g"], packet, bodies={"g": "z" * (GUIDE_BODY_CAP + 25)})
    assert len(packet.guide_bodies["g"]) == GUIDE_BODY_CAP
    assert "docs/harness/AGENTS.md" in packet.guides_loaded


def test_unknown_name_and_traversal_fail_closed():
    packet = ControlPacket(id="p")
    with pytest.raises(DemigodError, match="unknown demigod"):
        demigod_summon("not_a_demigod", packet)
    for bad in (
        "../x",
        "..",
        ".",
        "/etc/passwd",
        "themis.md",
        "themis/../../x",
        "a/b",
        "",
        "Themis",
        "demigod:themis",
    ):
        with pytest.raises(DemigodError, match="rejected demigod name"):
            demigod_summon(bad, packet)
    assert packet.guides_loaded == []
    assert packet.guide_bodies == {}
    with pytest.raises(DemigodError, match="rejected demigod name"):
        demigod_dismiss("../x", packet)


def test_empty_roster_fails_closed(monkeypatch):
    monkeypatch.setattr(router, "_iter_guide_names", lambda: [])
    packet = ControlPacket(id="p")
    with pytest.raises(DemigodError, match="empty demigod roster"):
        list_demigods()
    with pytest.raises(DemigodError, match="empty demigod roster"):
        demigod_search("themis")
    with pytest.raises(DemigodError, match="empty demigod roster"):
        demigod_summon("themis", packet)
    assert packet.guides_loaded == []


def test_roster_is_package_data_not_cwd():
    source = inspect.getsource(router)
    assert "Path.cwd" not in source
    assert "importlib.resources" in source
    text = files("resileos.kin.demigods").joinpath("guides", "themis.md")
    assert text.is_file()
    assert text.read_text(encoding="utf-8").startswith("# Themis")
    names = {item["name"] for item in list_demigods()}
    assert names == {"themis", "momus", "hephaestus", "nike", "atlas", "morpheus"}


def test_search_finds_by_description_and_rejects_blank_query():
    found = demigod_search("certifies")
    assert [item["name"] for item in found["results"]] == ["themis"]
    with pytest.raises(DemigodError, match="empty demigod search"):
        demigod_search("  ")
    assert demigod_search("no-such-word-zzz")["results"] == []


# ── Themis ──────────────────────────────────────────────────────────


def test_themis_verified_only_when_all_three_agree():
    result = themis_check(
        _packet(),
        {"status": "ok"},
        "turn 1: verified=True, scars=0",
    )
    assert result.verified is True
    assert result.success is True
    sources = [item["source"] for item in result.evidence]
    assert sources == ["residual_consistency", "apollo_success", "hades_lesson"]
    assert result.evidence[0]["result"]["consistent"] is True
    assert result.evidence[1]["result"]["success"] is True


def test_themis_disagreement_fails():
    result = themis_check(
        _packet(),
        {"status": "ok"},
        "turn 1: verified=False",
    )
    assert result.verified is False
    assert "lesson does not affirm" in result.reason


def test_themis_missing_evidence_fails():
    bare = ControlPacket(id="bare")
    missing_evidence = themis_check(bare, {"status": "ok"}, "verified=True")
    assert missing_evidence.verified is False
    assert "missing evidence" in missing_evidence.reason
    assert "evidence" in missing_evidence.reason

    missing_lesson = themis_check(_packet(), {"status": "ok"}, "no signal here")
    assert missing_lesson.verified is False
    assert "lesson" in missing_lesson.reason

    missing_apollo = themis_check(_packet(), None, "verified=True")
    assert missing_apollo.verified is False
    assert "apollo_result" in missing_apollo.reason

    missing_packet = themis_check(None, {"status": "ok"}, "verified=True")
    assert missing_packet.verified is False
    assert "packet" in missing_packet.reason


def test_themis_residual_hash_must_agree_and_core_is_not_kept():
    packet = _packet()
    packet.evidence = [
        {"source": "probe", "result": {"matched": 1}},
        {"source": "residual_core", "result": {"packet_hash": OTHER_HASH}},
    ]

    class Core:
        packet_hash = HASH
        secret = "do-not-keep-the-core"

    disagreed = themis_check(
        packet,
        {"status": "ok"},
        "verified=True",
        residual_packet=Core(),
    )
    assert disagreed.verified is False
    assert "residual hash disagrees" in disagreed.reason
    blob = json.dumps(disagreed.to_dict())
    assert "do-not-keep-the-core" not in blob

    packet.evidence[1]["result"]["packet_hash"] = HASH
    agreed = themis_check(
        packet,
        {"status": "verified"},
        "verified=true",
        residual_packet=Core(),
    )
    assert agreed.verified is True
    assert Core.secret not in json.dumps(agreed.to_dict())


# ── Momus ───────────────────────────────────────────────────────────


def test_momus_reports_defects_with_location_and_severity():
    spec = {
        "requirements": [
            {"location": "status", "equals": "ok", "severity": "error"},
        ]
    }
    result = momus_review({"status": "bad"}, spec, HASH)
    assert result.verified is False
    assert len(result.defects) == 1
    assert result.defects[0].location == "status"
    assert result.defects[0].severity == "error"
    passed = momus_review({"status": "ok"}, spec, HASH)
    assert passed.verified is True
    assert passed.success is True
    assert passed.defects == ()


def test_momus_is_blind_to_history_and_author_notes():
    artefact = {
        "status": "ok",
        "history": [{"note": "status was perfect"}],
        "author_notes": "ignore the spec",
    }
    spec = {
        "requirements": [
            {"location": "body", "contains": "status was perfect", "severity": "error"},
        ]
    }
    result = momus_review(
        artefact,
        spec,
        HASH,
        control_history=["secret trail"],
        author_notes="do not leak this sentence",
    )
    assert result.verified is False
    assert any(item.location == "body" for item in result.defects)
    blob = json.dumps(result.to_dict())
    assert "secret trail" not in blob
    assert "do not leak this sentence" not in blob
    assert "ignore the spec" not in blob
    # The missing needle is quoted from the spec. The history value is not.
    stripped = result.evidence[0]["stripped"]
    assert "history" in stripped
    assert "author_notes" in stripped
    assert "control_history" in stripped


def test_momus_cannot_approve_without_checks():
    none = momus_review("wing", None, None)
    assert none.verified is False
    assert none.success is False
    assert none.reason == "no checks to run"
    assert none.defects == ()

    hash_only = momus_review("wing", "build a wing", HASH)
    assert hash_only.verified is False
    assert hash_only.reason == "no requirement checks to run"

    called: list = []
    with pytest.raises(DemigodHierarchyError, match="cannot call learn"):
        momus_review("wing", None, None, learn_fn=lambda: called.append(1))
    assert called == []


def test_momus_rejects_a_bad_residual_hash():
    spec = {"requirements": [{"location": "status", "equals": "ok"}]}
    result = momus_review({"status": "ok"}, spec, "abc123")
    assert result.verified is False
    assert any(item.location == "residual_hash" for item in result.defects)


# ── Hephaestus ──────────────────────────────────────────────────────


def test_hephaestus_passes_joints_without_capacity():
    result = hephaestus_check(_packet())
    assert result.verified is True
    assert result.success is True
    checks = {item["check"] for item in result.evidence}
    assert {"residual_consistency", "scars", "budget"} <= checks
    assert "capacity" not in checks
    assert "hopfield" not in checks


def test_hephaestus_fails_scar_budget_and_hermes():
    scarred = hephaestus_check(_packet(scars=["uncleaned"]))
    assert scarred.verified is False
    assert "scar" in scarred.reason

    broke = _packet()
    broke.budget_remaining = {"steps": 0, "cost": 1.0, "tokens": 10}
    budget = hephaestus_check(broke)
    assert budget.verified is False
    assert "budget" in budget.reason

    hermes = HermesBudget(max_items=1, used=4)
    over_hermes = hephaestus_check(_packet(), hermes_budget=hermes)
    assert over_hermes.verified is False
    assert "hermes" in over_hermes.reason

    bad_hash = _packet()
    bad_hash.evidence = [
        {"source": "residual_core", "result": {"packet_hash": None}},
    ]
    inconsistent = hephaestus_check(bad_hash)
    assert inconsistent.verified is False
    assert inconsistent.evidence[0]["result"]["consistent"] is False


def test_atlas_capacity_uses_real_limits():
    under = atlas_check(_packet(), n_facts=hopfield_cap() - 1, dim=64, n_layers=3)
    assert under.verified is True
    names = {item["check"] for item in under.evidence}
    assert "hopfield" in names
    assert "mask_stack" in names

    over = atlas_check(_packet(), n_facts=hopfield_cap())
    assert over.verified is False
    assert over.success is False
    assert "cap" in over.reason

    mask = atlas_check(_packet(), dim=64, n_layers=11)
    assert mask.verified is False
    assert any(
        item["check"] == "mask_stack" and item["ok"] is False
        for item in mask.evidence
    )

    level = atlas_check(_packet(), dim=64, tower_level=20)
    assert level.verified is False
    assert "max_usable_level" in level.reason

    prim = atlas_check(_packet(), dim=64, primorial_k=4)
    assert prim.verified is False
    assert "n_usable_primorials" in prim.reason

    encoder = atlas_check(_packet(), dim=256, encoder_load=10_000)
    assert encoder.verified is False
    assert "default_capacity" in encoder.reason

    quiet = atlas_check(_packet())
    assert quiet.verified is True
    hop = next(item for item in quiet.evidence if item["check"] == "hopfield")
    assert hop["declared"] is False


def test_atlas_does_not_keep_the_residual_core():
    class Core:
        packet_hash = HASH
        secret = "atlas-must-not-keep"

    result = atlas_check(_packet(), n_facts=1, residual_packet=Core())
    assert result.verified is True
    assert "atlas-must-not-keep" not in json.dumps(result.to_dict())


# ── Nike ────────────────────────────────────────────────────────────


def test_nike_binary_success_and_no_criteria_fails():
    brief = "criterion: apollo:success\ncriterion: field:status=ok\n"
    passed = nike_check(
        task_brief=brief,
        artefact={"status": "ok"},
        apollo_result={"status": "ok"},
    )
    assert passed.success is True
    assert passed.verified is True

    partial = nike_check(
        task_brief=brief,
        artefact={"status": "bad"},
        apollo_result={"status": "ok"},
    )
    assert partial.success is False
    assert "field:status=ok" in partial.reason
    rows = partial.evidence[0]["results"]
    assert [row["ok"] for row in rows] == [True, False]

    no_criteria = nike_check(lesson="turn 4: verified=True, scars=0")
    assert no_criteria.success is False
    assert no_criteria.reason == "no explicit success criteria"

    no_channel = nike_check(task_brief="criterion: apollo:success")
    assert no_channel.success is False
    assert "missing residual or apollo evidence" in no_channel.reason


def test_nike_field_needs_residual_or_apollo_backing():
    backed = nike_check(
        task_brief="criterion: field:status=ok",
        artefact={"status": "ok"},
        apollo_result={"status": "scarred"},
        packet=ControlPacket(id="clean"),
    )
    assert backed.success is True

    packet = ControlPacket(id="scarred")
    packet.scars = ["open"]
    blocked = nike_check(
        task_brief="criterion: field:status=ok",
        artefact={"status": "ok"},
        apollo_result={"status": "scarred"},
        packet=packet,
    )
    assert blocked.success is False


# ── hierarchy ───────────────────────────────────────────────────────


def test_atlas_cannot_learn_or_summon():
    packet = ControlPacket(id="p")
    with demigod_duty("atlas"):
        with pytest.raises(DemigodHierarchyError, match="cannot call learn"):
            refuse_learn("A", "r", "b")
        with pytest.raises(DemigodHierarchyError, match="cannot summon"):
            demigod_summon("hephaestus", packet)
    assert packet.guides_loaded == []
    assert active_demigod() is None


def test_demigod_cannot_call_learn():
    with demigod_duty("nike"):
        with pytest.raises(DemigodHierarchyError, match="cannot call learn"):
            refuse_learn("Zeus", "domain", "sky")
    assert active_demigod() is None


def test_demigod_cannot_own_the_residual_core():
    class Core:
        packet_hash = HASH
        secret = "owned"

    with pytest.raises(DemigodHierarchyError, match="cannot own the residual core"):
        refuse_residual_ownership(Core())
    with pytest.raises(DemigodHierarchyError, match="cannot own the residual core"):
        momus_review({"status": "ok"}, None, HASH, residual_packet=Core())


def test_guides_stay_under_the_hygiene_cap():
    """Persona cards are rule text, well under the injection cap."""
    hygiene = 1200
    assert hygiene < GUIDE_BODY_CAP
    root = files("resileos.kin.demigods").joinpath("guides")
    for item in list_demigods():
        text = root.joinpath(f"{item['name']}.md").read_text(encoding="utf-8")
        assert len(text) <= hygiene
        assert len(text) < GUIDE_BODY_CAP
        assert "## Check" in text
        assert "## Evidence" in text


def test_momus_need_more_is_not_approval():
    spec = {"requirements": [{"location": "status", "equals": "ok"}]}
    missing_hash = momus_review({"status": "ok"}, spec, None)
    assert missing_hash.verified is False
    assert missing_hash.success is False
    assert missing_hash.outcome == OUTCOME_NEED_MORE
    assert any(item.code == "missing_residual_hash" for item in missing_hash.need_more)

    missing_field = momus_review({}, spec, HASH)
    assert missing_field.verified is False
    assert missing_field.outcome == OUTCOME_NEED_MORE
    assert missing_field.need_more[0].code == "missing_spec_field"
    assert missing_field.need_more[0].location == "status"

    bare = momus_review("wing", None, None)
    assert bare.outcome == OUTCOME_NEED_MORE
    assert bare.verified is False
    assert any(item.code == "missing_requirement" for item in bare.need_more)

    # A wrong present value is a fail, not a request for more fields.
    wrong = momus_review({"status": "bad"}, spec, HASH)
    assert wrong.outcome == "fail"
    assert wrong.verified is False
    assert wrong.need_more == ()


def test_need_more_round_fills_only_requested_fields(tmp_path):
    hades = Hades(store_dir=tmp_path / "hades")
    learned: list = []
    seen: list = []

    def maker(task, control):
        control.verified = True
        control.evidence = [{"source": "probe", "result": {"matched": 1}}]
        control.append({"event": "note", "author_notes": "SECRET-HISTORY"})
        return {"claims": [("Zeus", "domain", "sky")]}

    def supplement(request):
        seen.append(request)
        return {
            "status": "ok",
            "history": [{"note": "SECRET-HISTORY"}],
            "author_notes": "SECRET-HISTORY",
            "extra": "not-requested",
            "residual_hash": HASH,
        }

    spec = {"requirements": [{"location": "status", "equals": "ok"}]}
    out = maker_blind_verifier_cycle(
        "make it",
        maker,
        residual_packet=None,
        hades=hades,
        spec=spec,
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
        supplement_fn=supplement,
    )
    assert out["need_more_rounds"] == 1
    assert len(seen) == 1
    blob = json.dumps(seen[0])
    assert "SECRET-HISTORY" not in blob
    assert seen[0]["need_more"][0]["code"] == "missing_spec_field"
    assert "history" not in out["artefact"]
    assert "author_notes" not in out["artefact"]
    assert "extra" not in out["artefact"]
    assert out["artefact"]["status"] == "ok"
    assert out["findings"]["verified"] is True
    assert out["findings"]["outcome"] == "approved"
    assert learned == [("Zeus", "domain", "sky")]
    assert out["head"]["applied"] is True


def test_need_more_without_supplement_does_not_learn():
    learned: list = []

    def maker(task, control):
        control.verified = False
        return {}

    spec = {"requirements": [{"location": "status", "equals": "ok"}]}
    out = maker_blind_verifier_cycle(
        "make it",
        maker,
        spec=spec,
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
        residual_packet=type("Residual", (), {"packet_hash": HASH})(),
    )
    assert out["outcome"] == OUTCOME_NEED_MORE
    assert out["findings"]["verified"] is False
    assert out["need_more_rounds"] == 0
    assert out["head"]["applied"] is False
    assert learned == []


def test_need_more_round_cap_is_enforced():
    def maker(task, control):
        return {}

    with pytest.raises(DemigodError, match="capped"):
        maker_blind_verifier_cycle(
            "make it",
            maker,
            spec={"requirements": [{"location": "status", "equals": "ok"}]},
            max_rounds=MAX_NEED_MORE_ROUNDS + 1,
        )

    calls = {"n": 0}

    def supplement(_request):
        calls["n"] += 1
        return {}

    out = maker_blind_verifier_cycle(
        "make it",
        maker,
        spec={"requirements": [{"location": "status", "equals": "ok"}]},
        residual_packet=type("Residual", (), {"packet_hash": HASH})(),
        supplement_fn=supplement,
        max_rounds=1,
    )
    assert calls["n"] == 1
    assert out["need_more_rounds"] == 1
    assert out["findings"]["verified"] is False
    assert out["outcome"] == OUTCOME_NEED_MORE


def test_demigod_cannot_summon_another():
    packet = ControlPacket(id="p")
    with demigod_duty("themis"):
        with pytest.raises(DemigodHierarchyError, match="cannot summon"):
            demigod_summon("momus", packet)
    assert packet.guides_loaded == []
    assert active_demigod() is None


def test_demigod_cannot_persist_beyond_lesson_and_hash():
    with pytest.raises(DemigodHierarchyError, match="cannot persist"):
        durable_cross_attempt(
            {"lesson": "keep", "residual_hash": HASH, "history": ["nope"]}
        )
    assert durable_cross_attempt(
        {"lesson": "keep", "residual_hash": HASH}
    ) == {"lesson": "keep", "residual_packet_hash": HASH}


# ── tool surface ────────────────────────────────────────────────────


def test_demigod_tools_are_not_in_always_visible_catalogs():
    assert set(DEMIGOD_TOOLS).isdisjoint(ALWAYS_VISIBLE_TOOLS)
    visible = {row["name"] for row in always_visible_schemas()}
    assert set(DEMIGOD_TOOLS).isdisjoint(visible)
    answer = _answer_tools()
    answer_names = [item["name"] for item in answer.list_tool_schemas()]
    assert "demigod_summon" not in answer_names
    assert "themis" not in answer_names
    assert all(
        "demigod" not in item["function"]["name"] for item in answer.openai_tools()
    )
    assert "demigod_summon" not in answer.frame_index()
    app_text = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(
        encoding="utf-8"
    )
    assert "ALWAYS_VISIBLE_TOOLS as HARNESS_TOOLS" in app_text
    assert "import DEMIGOD_TOOLS" not in app_text
    assert "DEMIGOD_TOOLS =" not in app_text
    assert "search_tool_surface" in app_text


def test_tools_endpoint_lists_demigods_only_when_searched():
    import app

    listed = app.list_tools(q=None)
    harness_names = [row["name"] for row in listed["harness"]]
    assert "demigod_summon" not in harness_names
    assert "list_demigods" not in harness_names
    assert "search" not in listed
    tool_names = [row["name"] for row in listed["tools"]]
    assert "demigod_summon" not in tool_names

    searched = app.list_tools(q="momus")
    assert any(
        row["name"] == "momus" and row.get("kind") == "demigod"
        for row in searched["search"]["results"]
    )


def test_demigod_tools_are_reachable_by_search():
    assert search_tool_surface("")["results"] == []
    assert search_tool_surface("   ")["results"] == []
    found = search_tool_surface("demigod_summon")
    assert any(
        row["name"] == "demigod_summon" and row["deferred"] is True
        for row in found["results"]
    )
    themis = search_tool_surface("themis")
    assert any(
        row["name"] == "themis" and row.get("kind") == "demigod"
        for row in themis["results"]
    )
    assert "learn" not in DEMIGOD_TOOLS


# ── maker / blind verifier ──────────────────────────────────────────


def _maker(verified: bool):
    def maker(task, control):
        control.verified = verified
        control.evidence = [{"source": "probe", "result": {"matched": 1}}]
        control.append({"event": "note", "author_notes": "SECRET-HISTORY"})
        return {"status": "ok", "claims": [("Zeus", "domain", "sky")]}

    return maker


def test_cycle_learns_only_when_momus_approves(tmp_path):
    hades = Hades(store_dir=tmp_path / "hades")
    learned: list = []

    def learn(subject, relation, obj):
        assert active_demigod() is None
        learned.append((subject, relation, obj))

    spec = {"requirements": [{"location": "status", "equals": "ok"}]}
    residual = type("Residual", (), {"packet_hash": HASH})()
    out = maker_blind_verifier_cycle(
        "make it",
        _maker(True),
        residual_packet=residual,
        hades=hades,
        spec=spec,
        learn_fn=learn,
    )
    assert out["findings"]["verified"] is True
    assert out["findings"]["defects"] == []
    assert out["findings"]["demigod"] == "momus"
    assert learned == [("Zeus", "domain", "sky")]
    assert out["head"]["applied"] is True
    assert out["lesson"] and "verified=True" in out["lesson"]
    assert out["durable"] == {
        "lesson": out["lesson"],
        "residual_packet_hash": HASH,
    }
    assert "demigod:momus" not in out["review_guides"]
    assert out["guide_chars"] > 0
    assert "SECRET-HISTORY" not in json.dumps(out["findings"])

    learned.clear()
    rejected = maker_blind_verifier_cycle(
        "make it",
        _maker(True),
        residual_packet=residual,
        hades=hades,
        spec={"requirements": [{"location": "status", "equals": "perfect"}]},
        learn_fn=learn,
    )
    assert rejected["findings"]["verified"] is False
    assert rejected["findings"]["defects"][0]["location"] == "status"
    assert rejected["findings"]["defects"][0]["severity"] == "error"
    assert rejected["head"]["applied"] is False
    assert learned == []


def test_cycle_skips_lesson_when_control_is_not_verified(tmp_path):
    hades = Hades(store_dir=tmp_path / "unverified")
    learned: list = []
    spec = {"requirements": [{"location": "status", "equals": "ok"}]}
    out = maker_blind_verifier_cycle(
        "make it",
        _maker(False),
        residual_packet=type("Residual", (), {"packet_hash": HASH})(),
        hades=hades,
        spec=spec,
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
    )
    assert out["lesson"] is None
    assert out["lesson_skipped"] == "control.verified is false"
    assert hades.list_ids() == []
    assert out["findings"]["verified"] is True
    assert learned == [("Zeus", "domain", "sky")]
    assert out["durable"]["lesson"] is None


def test_cycle_does_not_learn_when_momus_has_no_checks():
    learned: list = []

    def maker(task, control):
        control.verified = False
        control.append({"author_notes": "SECRET-HISTORY"})
        return {"status": "ok", "claims": [("A", "r", "b")]}

    out = maker_blind_verifier_cycle(
        "build a wing",
        maker,
        learn_fn=lambda s, r, o: learned.append((s, r, o)),
    )
    assert out["findings"]["verified"] is False
    assert "no checks" in out["findings"]["reason"]
    assert learned == []
    assert "SECRET-HISTORY" not in json.dumps(out["findings"])
