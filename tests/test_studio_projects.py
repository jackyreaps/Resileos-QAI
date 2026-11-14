"""Studio app: projects per account, three pillars on one leveled core."""
import json
from pathlib import Path

import numpy as np
import pytest

from resileos.studio import level_core as core
from resileos.studio import projects as P
from resileos.studio import studio_ops as O
from resileos.substrate.suite_constants import PHI
from resileos.ui.cascade_address import CASCADE_FRAMES, frame_control, frame_weight, phi_address

ROOT = Path(__file__).resolve().parents[1]
PIC = np.random.default_rng(3).random((18, 22, 3)).round(3).tolist()
PIC2 = np.random.default_rng(4).random((18, 22, 3)).round(3).tolist()


@pytest.fixture(autouse=True)
def studio_dir(tmp_path, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.setenv("RESILEOS_STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    return tmp_path / "studio"


# ── leveled core ───────────────────────────────────────────────────────

def test_levels_are_frame_grids_at_the_phi_address_not_a_halving_pyramid():
    levels = core.level_down(PIC)
    assert [b["frame"] for b in levels["bands"]] == list(CASCADE_FRAMES)
    for b in levels["bands"]:
        assert b["control"] == frame_control(b["frame"])
        assert b["address"] == round(frame_weight(b["frame"]), 6)
    assert core.grid(PIC, 3).shape[:2] == (3, 3) and core.grid(PIC, 5).shape[:2] == (5, 5)
    assert core.grid(PIC, 9).shape[:2] == (9, 9) and core.grid(PIC, 12).shape[:2] == (12, 12)
    # Lossless with the detail band; frame 5 is the pentagram orientation.
    full = core.level_up(levels, 12, detail=True)
    assert np.abs(full - np.asarray(PIC)).max() < 1e-9
    assert levels["bands"][1]["control"]["figure"] == "pentagram"
    with pytest.raises(ValueError):
        core.grid(PIC, 4)
    with pytest.raises(ValueError):
        core.keyframes(10, 8)


def test_one_core_serves_image_video_and_world():
    assert core.keyframes(12, 3) == [0, 6, 11] and len(core.keyframes(24, 9)) == 9
    clip = core.clip_at([PIC, PIC2, PIC, PIC2, PIC], 3)
    assert clip["keyframes"] == [0, 2, 4] and clip["frame"]["frame"] == 3
    project = P.clean({"name": "W", "bible": {"places": [{"name": "Harbor"}]}, "scenes": [{"title": "Dock"}]})
    assert [n["kind"] for n in core.world_at(project, 3)["nodes"]] == ["world"]
    assert "place" in [n["kind"] for n in core.world_at(project, 5)["nodes"]]
    assert "scene" in [n["kind"] for n in core.world_at(project, 9)["nodes"]]


def test_sub_instances_reach_frame_12_at_full_strength():
    deep = core.Overlay("a", children=[core.Overlay("b", children=[core.Overlay("c", children=[core.Overlay("d", children=[core.Overlay("e")])])])])
    out = core.instances(deep)
    got = out["instances"]
    assert [i["frame"] for i in got] == [3, 5, 9, 12]
    assert [i["address"] for i in got] == [round(phi_address(f) / phi_address(3), 6) for f in (3, 5, 9, 12)]
    assert all(i["strength"] == 1.0 for i in got)  # the address places, it never dims
    assert out["stopped"] == {"floor": 0, "waist": 0, "depth": 1}
    # The span is block-size metadata: 12 at frame 3, 4 at 9, 3 at 12; frame 5 has none.
    assert [i["span"] for i in got] == [12, None, 4, 3]
    assert core.frame_control(5)["span"] is None
    # The waist of 36 is the only total limit; the span is not a fan-out cap.
    wide = core.instances(core.Overlay("root", children=[core.Overlay(f"c{i}") for i in range(60)]))
    assert len(wide["instances"]) == 36 and wide["stopped"]["waist"] == 25
    assert wide["instances"][0]["span"] == 12 and all(i["span"] is None for i in wide["instances"][1:])
    nine = core.instances(core.Overlay("a", children=[core.Overlay("b", children=[core.Overlay(f"c{i}") for i in range(10)])]))
    assert len(nine["instances"]) == 12 and nine["instances"][-1]["span"] == 4  # 10 frame-9 copies, not capped at 4
    # The 1/64 floor is on a sub-instance's own residual energy only.
    quiet = core.instances(core.Overlay("a", children=[core.Overlay("b", energy=0.01), core.Overlay("c", energy=0.02)]))
    assert [i["name"] for i in quiet["instances"]] == ["a", "c"] and quiet["stopped"]["floor"] == 1
    base = np.zeros((4, 4, 3))
    top = np.ones((4, 4, 3))
    weak, strong = core.Overlay("w", strength=1, alpha=1.0, payload=top * 0.2), core.Overlay("s", strength=2, alpha=0.5, payload=top)
    assert core.compose(base, [strong, weak])[0, 0, 0] == pytest.approx(0.6)
    assert core.merge({"x": 1}, [core.Overlay("o", strength=1, payload={"x": 2})]) == {"x": 2}


# ── projects: per account, individual tier ─────────────────────────────

def test_projects_are_per_account_and_need_sign_in():
    a = P.save_project("acct:a", {"name": "Ash"})
    assert P.list_projects("acct:a")[0]["id"] == a["id"]
    assert P.list_projects("acct:b") == []
    with pytest.raises(KeyError):
        P.get_project("acct:b", a["id"])
    with pytest.raises(PermissionError):
        P.list_projects("trial:1.2.3.4")
    assert a["tier"] == "individual" and a["learned"] is False


def test_characters_link_the_persona_individual_tier_without_promotion():
    p = P.clean({"characters": [{"name": "Ira", "voice": "honest"}]})
    persona = p["characters"][0]["persona"]
    assert persona["tier"] == "individual" and persona["promotes"] is False and persona["pin"].startswith("5/5/")


def test_timeline_quintuples_and_conflicts():
    p = P.clean({"bible": {"timeline": [
        {"subject": "Ira", "relation": "rules", "object": "Harbor", "valid_from": "1200", "valid_to": "1250"},
        {"subject": "Ira", "relation": "rules", "object": "Hill", "valid_from": "1240", "valid_to": "1260"},
        {"subject": "Ira", "relation": "rules", "object": "Vale", "valid_from": "1300"},
        {"subject": "Bo", "relation": "born", "object": "Vale", "valid_from": "1300", "valid_to": "1200"},
    ]}})
    out = P.check_timeline(p["bible"]["timeline"])
    kinds = sorted(x["kind"] for x in out["problems"])
    assert kinds == ["order", "overlap"]
    with pytest.raises(ValueError):
        P.clean({"bible": {"timeline": [{"subject": "a", "relation": "b", "object": "c", "valid_from": "soon"}]}})


def test_game_rules_and_invariants():
    game = {"stats": [{"name": "hp", "min": 0, "max": 10, "start": 10}],
            "entities": [{"name": "Knight", "stats": {"hp": 10}}],
            "rules": [{"name": "poison", "stat": "hp", "change": -3}],
            "invariants": [{"stat": "hp", "op": ">=", "value": 2}]}
    out = P.check_game(P.clean({"game": game})["game"])
    assert not out["ok"] and out["problems"][0]["round"] == 3
    src = P.game_lean_source(P.clean({"game": game})["game"])
    assert "theorem hp_start_in_range" in src and "by decide" in src
    _, res = O.game_lean(P.clean({"game": game}), {}, lean_fn=lambda s: {"status": "CHECKED", "summary": "Proof checks."})
    assert res["status"] == "CHECKED"


def test_dreams_are_labelled_and_never_learned():
    p = P.clean({"bible": {"places": [{"name": "Harbor"}], "factions": [{"name": "Tide"}]}, "characters": [{"name": "Ira"}]})
    out = P.dream(p, n=3)
    assert out["verified"] is False and out["learned"] is False
    assert all(i["verified"] is False and i["label"] == "Dream — not checked" for i in out["ideas"])
    assert P.dream(p, n=3) == out


# ── pillars ────────────────────────────────────────────────────────────

def _proj():
    p = P.clean({"name": "T"})
    p, a = O.add_asset(p, {"matrix": PIC, "name": "one"})
    p, b = O.add_asset(p, {"matrix": PIC2, "name": "two"})
    return p, a["asset"]["id"], b["asset"]["id"]


def test_image_pillar_variations_orientation_layers_batch_pick():
    p, a, b = _proj()
    assert p["assets"][0]["code"] and p["assets"][0]["address"]["path"].startswith("5/5/")
    p, v = O.variations(p, {"asset": a, "n": 3, "orientation": "orion"})
    assert len(v["made"]) == 3 and all(m["parent"] == a and m["verified"] is False for m in v["made"])
    assert v["details"]["orientation"]["frame"] == 9
    p, e = O.edit(p, {"assets": [a, b], "layers": [{"kind": "tone", "brightness": 0.1}, {"kind": "level", "frame": 5},
                                                  {"kind": "overlay", "asset": b, "alpha": 0.4}, {"kind": "flip"}]})
    assert len(e["made"]) == 2
    p, _ = O.pick(p, {"asset": e["made"][1]["id"]})
    assert p["picks"][0] == e["made"][1]["id"]
    _, lv = O.level_preview(p, {"asset": a})
    assert [l["frame"]["frame"] for l in lv["levels"]] == [3, 5, 9, 12]


def test_video_pillar_clips_and_unavailable_provider():
    p, a, b = _proj()
    p, one = O.clip_from_pictures(p, {"assets": [a]})
    assert one["made"][0]["kind"] == "clip" and len(one["made"][0]["frames"]) == 12
    p, two = O.clip_from_pictures(p, {"assets": [a, b]})
    p, rc = O.recolor_clip(p, {"asset": two["made"][0]["id"], "variant": 2})
    assert len(rc["made"][0]["frames"]) == len(two["made"][0]["frames"])
    p["scenes"] = [{"id": "s1", "title": "Dock", "shots": [{"asset": a, "hold": 2}, {"asset": b, "hold": 1}], "characters": []}]
    p, sb = O.storyboard_clip(P.clean(p), {"scene": "s1"})
    assert sb["details"]["shots"] == 2 and sb["made"][0]["kind"] == "clip"
    _, t2v = O.text_to_video(p, {"prompt": "a fox"})
    assert t2v["status"] == "UNAVAILABLE" and t2v["made"] == [] and t2v["url"] is None


def test_studio_never_learns_or_writes_titanos(monkeypatch):
    import resileos.studio.studio_ops as ops_mod

    import ast

    for name in ("studio_ops.py", "projects.py", "level_core.py", "project_routes.py"):
        tree = ast.parse((ROOT / "src/resileos/studio" / name).read_text())
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {k.arg for n in ast.walk(tree) if isinstance(n, ast.Call) for k in n.keywords if k.arg}
        for banned in ("learn", "learn_fn", "write_scar", "add_scar", "scars", "commit_facts", "eat_commit_envelopes", "add_quintuple"):
            assert banned not in used, (name, banned)
    p = P.clean({"bible": {"timeline": [{"subject": "Ira", "relation": "rules", "object": "Harbor", "valid_from": "1200"}]}})
    with pytest.raises(ValueError):
        ops_mod.promote_preview(p, {})
    _, out = ops_mod.promote_preview(p, {"opt_in": True}, lean_fn=lambda s: {"status": "CHECKED"})
    assert out["saved"] == 0 and "Ira,rules,Harbor,1200-01-01" in out["csv"].replace("\r", "")
    assert out["preview"]["ready"] == 1


# ── HTTP ───────────────────────────────────────────────────────────────

def test_routes_create_with_chat_handoff_run_ops_and_stream(client):
    res = client.post("/api/v1/studio-projects", json={"name": "From chat", "from_chat": {"matrix": PIC, "name": "fox.png"}})
    assert res.status_code == 200, res.text
    p = res.json()
    assert p["assets"][0]["source"] == "chat"
    pid, aid = p["id"], p["assets"][0]["id"]
    lst = client.get("/api/v1/studio-projects").json()
    assert lst["projects"][0]["id"] == pid and lst["video_provider"]["status"] == "UNAVAILABLE"
    # Saving from the client never replaces picture data.
    body = client.get(f"/api/v1/studio-projects/{pid}").json()
    body["assets"][0]["matrix"] = [[0]]
    body["assets"][0]["name"] = "renamed"
    body["bible"]["lore"] = [{"title": "Origin", "text": "Salt and stone."}]
    saved = client.put(f"/api/v1/studio-projects/{pid}", json=body).json()
    assert saved["assets"][0]["name"] == "renamed" and saved["assets"][0]["matrix"] == p["assets"][0]["matrix"]
    out = client.post(f"/api/v1/studio-projects/{pid}/op/variations", json={"asset": aid, "n": 2}).json()
    assert len(out["result"]["made"]) == 2 and len(out["project"]["assets"]) == 3
    assert client.post(f"/api/v1/studio-projects/{pid}/op/nope", json={}).status_code == 404
    stream = client.post(f"/api/v1/studio-projects/{pid}/stream/text_to_video", json={"prompt": "a fox"})
    assert stream.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(l[6:]) for l in stream.text.splitlines() if l.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done" and "abstain" in types
    final = next(e for e in events if e["type"] == "final")
    assert final["status"] == "UNAVAILABLE" and final["verified"] is False
    s2 = client.post(f"/api/v1/studio-projects/{pid}/stream/clip", json={"assets": [aid]})
    ev2 = [json.loads(l[6:]) for l in s2.text.splitlines() if l.startswith("data: ")]
    assert any(e["type"] == "address" for e in ev2) and any(e["type"] == "step" for e in ev2)
    assert client.delete(f"/api/v1/studio-projects/{pid}").json() == {"deleted": True}


def test_project_paths_are_public_on_both_sides():
    from middleware import proxy_identity as PI

    for method, path in (("GET", "/api/v1/studio-projects"), ("POST", "/api/v1/studio-projects"),
                         ("PUT", "/api/v1/studio-projects/abc"), ("POST", "/api/v1/studio-projects/abc/op/edit"),
                         ("POST", "/api/v1/studio-projects/abc/stream/clip")):
        assert PI.is_public(method, path), path
    js = (ROOT / "landing/functions/_admin.js").read_text()
    assert '["POST", ["studio-projects", "*", "stream", "*"]]' in js


def test_studio_is_its_own_app_shell_with_plain_labels():
    import re

    html = (ROOT / "landing/public/studio.html").read_text()
    js = (ROOT / "landing/public/assets/studio-app.js").read_text()
    views = set(re.findall(r'<section class="sa-view[^"]*" data-view="(\w+)"', html))
    assert views == {"projects", "world", "characters", "scenes", "game", "video", "image", "assets", "make"}
    assert set(re.findall(r'<a href="#\w+" data-view="(\w+)"', html)) == views
    for script in ("/assets/stream-parts.js", "/assets/studio.js", "/assets/studio-app.js"):
        assert script in html
    visible = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    for jargon in ("chroma", "residual", "Kuramoto", "quintuple", "phi", "Morpheus", "Titanos"):
        assert jargon.lower() not in visible.lower(), jargon
    assert '"/api/session/v1/studio-projects"' in js
    assert "We won't pretend" in js and "not checked" in js
    assert "/stream/" in js and "ResileosParts.run" in js  # shares the stream layer
    assert "__studioHandoff" in (ROOT / "landing/public/assets/studio.js").read_text()


# ── Muse: the native generative leaf under Apollo ─────────────────────
from resileos.kin import studio_tools as ST  # noqa: E402
from resileos.studio.clip_metrics import phase_band_coherence  # noqa: E402

WORLD = {"id": "0123456789abcdef", "name": "Salt Coast",
         "bible": {"places": [{"id": "pa", "name": "Harbor"}, {"id": "pb", "name": "Hill Fort"}],
                   "factions": [{"id": "fa", "name": "Guild"}], "timeline": [], "lore": []},
         "scenes": [{"id": "s1", "title": "Arrival", "place": "pa", "shots": [{"asset": "x1", "hold": 1}]},
                    {"id": "s2", "title": "Nowhere", "place": "", "shots": []}],
         "game": {"stats": [{"name": "hp", "min": 0, "max": 10, "start": 5}],
                  "entities": [{"id": "e1", "name": "Hero", "stats": {"hp": 5}}],
                  "rules": [{"id": "r1", "name": "rest", "stat": "hp", "change": 1}],
                  "invariants": [{"id": "i1", "stat": "hp", "op": ">=", "value": 0}]}}


def _block(shift=0):
    a = np.zeros((24, 24, 3))
    a[8:14, 2 + shift:8 + shift] = [1.0, 0.5, 0.2]
    return a


def test_phase_inbetween_moves_instead_of_cross_fading():
    a, b = _block(0), _block(10)
    mid = core.phase_inbetween(a, b, 0.5)
    cols = mid[..., 0].mean(axis=0)
    fade = ((a + b) / 2)[..., 0].mean(axis=0)
    # The block sits halfway (cols 7..12), not as two half-bright ghosts at 2..7 and 12..17.
    assert int(np.argmax(cols)) in range(7, 13) and cols[2] < 0.05 and cols[16] < 0.05
    assert fade[2] > 0.1 and fade[16] > 0.1
    assert np.allclose(core.phase_inbetween(a, b, 0.0), a) and np.allclose(core.phase_inbetween(a, b, 1.0), b)
    # Same time steps as before: held keyframes, in-betweens at j/per.
    clip = core.phase_clip([a, b, a], per=3, holds=[2, 1, 1])
    assert len(clip) == 2 + 2 + 1 + 2 + 1


def test_per_level_kuramoto_coherence_tells_smooth_from_jitter():
    x = np.random.default_rng(0).random((24, 24))
    smooth = [np.roll(x, t, axis=1) for t in range(8)]
    jitter = [np.roll(x, int(s), axis=1) for s in (0, 3, 1, 5, 2, 6, 0, 4)]
    a, b = phase_band_coherence(smooth), phase_band_coherence(jitter)
    assert set(a["levels"]) == {"3", "5", "9", "12", "detail"}
    assert a["R"] > b["R"] + 0.2
    assert phase_band_coherence(smooth[:2])["R"] is None  # needs two transitions


def test_leveled_wfc_environment_nests_and_keeps_the_frame_rules():
    env = core.environment(WORLD)
    assert env["ok"] and env == core.environment(WORLD) | {"map": env["map"]}  # deterministic
    r, t = env["regions"]["grid"], env["tiles"]["grid"]
    assert len(r) == 3 and len(t) == 9  # frame 3 (span 12) and frame 9 (span 4) on the 36 lattice
    assert env["regions"]["frame"]["span"] == 12 and env["tiles"]["frame"]["span"] == 4
    assert env["regions"]["adjacency_ok"] and env["tiles"]["adjacency_ok"] and env["tiles"]["nested_in_regions"]
    # Places sit at frame 5: orientation, no span, no tiles.
    assert all(p["frame"] == 5 and p["region_kind"] != "sea" for p in env["places"])
    assert frame_control(5)["span"] is None
    # Frame 12 detail is not built until the inheritance rule is chosen.
    assert env["detail"]["built"] is False
    assert env["map"].shape == (36, 36, 3) and env["map"].max() > 0.9  # full-strength colour
    # Scene graph: world 3 -> place 5 -> scene 9 -> shot asset 12.
    frames = {i["name"]: i["frame"] for i in env["scene_graph"]["instances"]}
    assert frames == {"Salt Coast": 3, "Harbor": 5, "Arrival": 9, "x1": 12, "Hill Fort": 5}
    assert not core.adjacency_ok([["sea", "mountain"]], core.REGION_TILES)


def test_muse_is_an_apollo_legion_that_returns_evidence_never_facts(tmp_path):
    from resileos.harness.packet import ControlPacket
    from resileos.kin.hades import Hades
    from resileos.kin.legions import kin_catalogue

    ST.register_studio_legions()
    assert "muse" in [r["name"] for r in kin_catalogue("apollo")]
    from resileos.kin import legions as L

    assert "muse" not in L._KIN  # a legion, not a Kin
    pkt = ControlPacket(id="m1", budget_remaining=dict(ST.MUSE_BUDGET))
    hades = Hades(tmp_path / "hades")
    out = ST.run_muse({"kind": "clip", "keyframes": [_block(0), _block(6)], "per": 4}, packet=pkt, hades=hades)
    assert out["status"] == "MADE" and out["verified"] is False and out["is_fact"] is False
    assert 0.0 < out["confidence"] <= 1.0 and set(out["cost"]) == {"seconds", "memory_mb"}
    assert pkt.generative_source == "muse/native:clip" and pkt.generative_evidence_id == out["generative_evidence_id"]
    assert pkt.generative_cost == out["cost"] and pkt.verified is False
    assert pkt.budget_remaining["seconds"] < ST.MUSE_BUDGET["seconds"]
    d = pkt.to_dict()
    assert {"generative_source", "generative_cost", "generative_evidence_id"} <= set(d)
    # Hades keeps one line.
    files = list((tmp_path / "hades").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["lesson"] == out["lesson"] and "\n" not in saved["lesson"]
    assert "frames" not in json.dumps(saved)
    # Even with an Apollo success claim, Muse never verifies.
    direct = L.invoke_legion("apollo", "muse", {"id": "x", "budget_remaining": dict(ST.MUSE_BUDGET), "evidence": [{"raw": 1}]},
                             brief={"kind": "environment", "project": WORLD}, apollo_result={"success": True})
    assert direct["verified"] is False
    # No learn, scar or Titanos in Muse.
    import ast
    import inspect

    for fn in (ST.muse, ST.run_muse, ST._muse_clip, ST._muse_environment, ST._muse_text_video):
        names = {n.id for n in ast.walk(ast.parse(inspect.getsource(fn))) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(ast.parse(inspect.getsource(fn))) if isinstance(n, ast.Attribute)}
        assert not names & {"learn", "scars", "scar", "Titanos", "titanos", "eat_commit_envelopes"}, fn.__name__


def test_muse_budget_counts_time_and_memory():
    from resileos.harness.tools import budget_and_stuck_guard

    assert budget_and_stuck_guard({"budget_remaining": {"seconds": 0}, "history": []})["ok"] is False
    assert budget_and_stuck_guard({"budget_remaining": {"memory_mb": -1}, "history": []})["ok"] is False
    spent = ST.run_muse({"kind": "environment", "project": WORLD}, packet={"id": "b", "budget_remaining": {"seconds": 0.0}})
    assert spent["status"] == "OVER_BUDGET" and spent["evidence"] is None
    tight = {"id": "c", "budget_remaining": {"seconds": 30.0, "memory_mb": 0.001}}
    over = ST.run_muse({"kind": "environment", "project": WORLD}, packet=tight)
    assert over["status"] == "OVER_BUDGET" and over["evidence"] is None and tight["budget_remaining"]["memory_mb"] < 0


def test_muse_is_not_on_the_confidence_cascade():
    for path in ("src/resileos/harness/cascade.py", "src/resileos/harness/tools.py", "src/resileos/chat/router.py",
                 "src/resileos/chat/cascade_tools.py"):
        assert "muse" not in (ROOT / path).read_text().lower(), path


def test_text_only_video_is_unavailable_and_a_scene_in_the_world_is_native():
    no_scene = ST.run_muse({"kind": "text_video", "project": WORLD, "prompt": "a lighthouse"})
    assert no_scene["status"] == "UNAVAILABLE" and no_scene["url"] is None and no_scene["evidence"] is None
    homeless = ST.run_muse({"kind": "text_video", "project": WORLD, "scene": "s2", "prompt": "x"})
    assert homeless["status"] == "UNAVAILABLE" and homeless["url"] is None
    made = ST.run_muse({"kind": "text_video", "project": WORLD, "scene": "s1", "prompt": "x"})
    assert made["status"] == "MADE" and made["url"] is None and len(made["evidence"]["frames"]) == 12
    assert "not turned into pictures" in made["evidence"]["method"] and made["evidence"]["place"] == "Harbor"
    p, out = O.text_to_video(P.clean(dict(WORLD)), {"prompt": "x", "scene": "s1"})
    assert out["status"] == "MADE" and out["made"][0]["kind"] == "clip" and out["url"] is None
    _, none = O.text_to_video(P.clean(dict(WORLD)), {"prompt": "a lighthouse"})
    assert none["status"] == "UNAVAILABLE" and none["url"] is None and none["made"] == []


def test_studio_clips_and_worlds_use_muse():
    p = P.clean({"name": "M"})
    p, a = O.add_asset(p, {"kind": "image", "matrix": _block(0).tolist(), "name": "a"})
    p, b = O.add_asset(p, {"kind": "image", "matrix": _block(6).tolist(), "name": "b"})
    p, clip = O.clip_from_pictures(p, {"assets": [a["asset"]["id"], b["asset"]["id"]], "frames": 8})
    assert clip["details"]["source"] == "muse/native:clip" and "phase_band_coherence" in clip["details"]["metrics"]
    p["bible"]["places"] = [{"id": "pa", "name": "Harbor"}]
    p, world = O.build_world(P.clean(p), {})
    assert world["status"] == "MADE" and world["made"][0]["name"] == "World map"
    assert world["details"]["source"] == "muse/native:environment" and world["verified"] is False
    assert any("Harbor is in the" in line for line in world["summary"])
    assert "build_world" in O.OPS
