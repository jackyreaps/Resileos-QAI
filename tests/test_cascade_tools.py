"""Tools built from the cascade math: addresses, ranking, variations,
clips, and content-free use factors. No provider, no learning."""
from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from resileos.chat import cascade_tools as C
from resileos.ui.cascade_address import BELT, EPSILON, WAIST
from resileos.ui.chroma import CODE_BYTES, unpack_code


def picture(h=24, w=32):
    img = np.zeros((h, w, 3))
    img[...] = [0.1, 0.15, 0.25]
    img[6:18, 8:20] = [0.9, 0.35, 0.1]
    return img


def test_belt_coords_split_black_white_and_rby():
    px = np.array([[[1.0, 1.0, 1.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [1.0, 1.0, 0.0]]])
    coords = C.belt_coords(px)[0]
    assert coords[0].tolist() == [0, 1, 0, 0, 0]  # white
    assert coords[1].tolist() == [1, 0, 0, 0, 0]  # black
    assert coords[2].tolist() == [0, 0, 1, 0, 0]  # red
    assert coords[3].tolist() == [0, 0, 0, 1, 0]  # blue
    assert coords[4].tolist() == [0, 0, 0, 0, 1]  # yellow


def test_upload_gets_a_pin_address_and_a_reusable_code():
    out = C.address_upload("image", {"mean_luma": 0.3, "edge_density": 0.2}, matrix=picture())
    addr = out["address"]
    assert addr["pin"] == "individual" and addr["belt"] == BELT and addr["frame"] == 5 and addr["waist"] == WAIST
    assert addr["path"].startswith("5/5/")
    raw = bytes.fromhex(out["code"])
    assert len(raw) == CODE_BYTES
    assert unpack_code(raw)["orientation"] == out["chroma_code"]["orientation"]
    text = C.address_upload("text", {}, text="hello world")
    assert text["chroma_code"] is None and text["address"]["pin"] == "individual"


def test_rank_sources_cascade_floor_and_waist():
    rows = [{"title": f"Lean {i}", "url": f"https://s{i}.example", "snippet": "Lean theorem prover"} for i in range(40)]
    rows[1]["snippet"] = "nothing relevant"
    rows[1]["title"] = "cats"
    out = C.rank_sources(rows, "Lean theorem prover")
    urls = [e["source"] for e in out["envelopes"]]
    assert "https://s1.example" not in urls  # relevance 0 is below 1/64
    assert len(out["envelopes"]) <= 12  # outer frame stays 12
    assert all(e["score"] >= EPSILON for e in out["envelopes"])
    assert [e["address"]["frame"] for e in out["envelopes"][:3]] == [3, 3, 5]
    scores = [e["score"] for e in out["envelopes"]]
    assert scores == sorted(scores, reverse=True)
    assert out["envelopes"][0]["trust"] == "untrusted"
    many = C.rank_sources(rows[:12] * 4, "Lean")
    assert len(many["envelopes"]) <= WAIST


def test_variations_are_real_and_keep_structure():
    out = C.variations_from_code(picture(), n=4)
    assert out["made"] and len(out["variations"]) == 4
    mats = [np.array(v["matrix"]) for v in out["variations"]]
    # Different from each other.
    assert len({m[12, 12].round(2).tobytes() for m in mats}) >= 3
    # Brightness (value) of the original is kept, so the shape is still there.
    value = picture().max(axis=2)
    for m in mats:
        assert np.allclose(m.max(axis=2), value, atol=0.02)
    again = C.variations_from_code(picture(), n=4, code=out["code"])
    assert again["variations"][0]["matrix"] == out["variations"][0]["matrix"]


def test_clip_from_picture_moves_with_phi_and_records_metrics():
    out = C.clip_from_code(picture(), frames=8)
    assert out["made"] and len(out["frames"]) == 8
    m = out["check_metrics"]
    assert m["version"] == "clip-metrics/1" and m["gating"] is False
    assert m["moving_transitions"] == 7
    assert m["motion_phase_coherence"] == pytest.approx(1.0)


def test_recolor_clip_keeps_every_frame():
    frames = [picture() * (0.8 + 0.05 * t) for t in range(4)]
    out = C.recolor_clip(frames)
    assert len(out["frames"]) == 4
    with pytest.raises(ValueError):
        C.recolor_clip([picture()])


def test_factor_pool_is_content_free_and_needs_three(tmp_path):
    from resileos.persona.residual_factors import contains_content

    pool = C.FactorPool(tmp_path / "f.jsonl")
    addr = C.address_upload("image", {"mean_luma": 0.3, "edge_density": 0.2}, matrix=picture())
    assert C.use_factor(addr, verified=False) is None  # unverified never counts
    assert C.use_factor(addr, verified=True, opt_out=True) is None
    rec = C.use_factor(addr, verified=True, orientation="edge")
    assert rec and pool.add(rec)
    assert pool.hub_aggregate()["aggregate"]["ok"] is False  # below 3 contributors
    pool.add(rec)
    pool.add(rec)
    hub = pool.hub_aggregate()
    assert hub["aggregate"]["ok"] and hub["aggregate"]["eat"] == "pending"
    assert hub["learned"] is False and hub["writes"] is False
    assert hub["dreams"]["verified"] is False and hub["dreams"]["candidates"]
    blob = (tmp_path / "f.jsonl").read_text()
    assert not contains_content(blob, ["fox.png", "Alice works at Acme"], pixels=[picture()])


def test_assist_counts_factors_only_when_verified_and_never_from_files(tmp_path):
    from resileos.chat import assist as A

    pool = C.FactorPool(tmp_path / "f.jsonl")
    img = picture(6, 8).tolist()

    async def chat_fn(*a, **k):
        return {"status": "ACCEPTED", "value": "ok", "verified": True}

    def go(**body):
        return asyncio.run(A.run_assist(A.AssistBody(**body), titanos=None, chat_fn=chat_fn, factor_pool=pool, crawl_top=0))

    out = go(message="what is this?", attachments=[{"name": "p.png", "kind": "image", "matrix": img}])
    assert out["assist"]["factors_counted"] == 1
    out = go(message="what is this?", attachments=[{"name": "p.png", "kind": "image", "matrix": img, "file_id": "a" * 32}])
    assert out["assist"]["factors_counted"] == 0
    out = go(message="what is this?", factors_opt_out=True, attachments=[{"name": "p.png", "kind": "image", "matrix": img}])
    assert out["assist"]["factors_counted"] == 0
    assert len(pool.records()) == 1


def test_studio_endpoints(client, monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.setenv("RESILEOS_FACTORS_PATH", str(tmp_path / "f.jsonl"))
    img = picture().tolist()
    var = client.post("/api/v1/studio/variations", json={"matrix": img, "n": 3})
    assert var.status_code == 200 and len(var.json()["variations"]) == 3
    clip = client.post("/api/v1/studio/clip-from-picture", json={"matrix": img, "frames_out": 6})
    assert clip.status_code == 200 and len(clip.json()["frames"]) == 6
    assert client.post("/api/v1/studio/variations", json={}).status_code == 400
    hub = client.get("/api/v1/factors/hub")
    assert hub.status_code == 200 and hub.json()["learned"] is False


def test_cascade_tools_never_learn():
    from pathlib import Path

    text = Path(C.__file__).read_text(encoding="utf-8")
    assert ".learn(" not in text and "eat_commit_envelopes" not in text
