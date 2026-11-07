"""Smoke test for perception helpers."""
from resileos.ui.perception import triples_from_caption, perception_payload


def test_triples_from_caption():
    t = triples_from_caption("a red car on a road", subject="photo1")
    rels = {x["relation"] for x in t}
    assert "has_color" in rels
    assert "depicts" in rels
    assert "located_on" in rels


def test_payload_shape():
    p = perception_payload("blue sky")
    assert "candidates" in p
    assert p["candidates"]
