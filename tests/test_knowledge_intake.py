"""Admin → Knowledge → Add facts: preview writes nothing, commit goes through Eat."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from titanos import Titanos, TitanosConfig

from resileos.kin import knowledge_intake as K

from test_proxy_identity import admin_headers, keys  # noqa: F401  (fixture)


def _titanos():
    return Titanos(TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=6, seed=42, classical_conf=0.09, abstention_gate=0.035,
        sigma_E=10.0, sigma_k=3, E_sat=10.0, E_sigma=10.0, tau_sat=0.9, tau_low=0.1,
    ))


PASTE = """# notes
Athens | capital_of | Greece | 1834-01-01
| subject | relation | object |
|---|---|---|
| Lisbon | capital_of | Portugal |
(Acme, based_in, Lisbon)
Everyone knows Acme is the best company around.
Acme is probably in Porto, I think.
"""


def test_extract_formats():
    got = K.extract("paste.md", PASTE)
    assert got["facts"] == [
        {"subject": "Athens", "relation": "capital_of", "obj": "Greece", "valid_from": "1834-01-01"},
        {"subject": "Lisbon", "relation": "capital_of", "obj": "Portugal"},
        {"subject": "Acme", "relation": "based_in", "obj": "Lisbon"},
    ]
    assert len(got["prose"]) == 2
    csv_text = "subject,relation,object,valid_from,valid_to\nAthens,capital_of,Ottoman Empire,1458-01-01,1834-01-01\nnot a row\n"
    assert K.extract("a.csv", csv_text)["facts"][0]["valid_to"] == "1834-01-01"
    assert K.extract("a.csv", "x,y,z\n")["facts"] == [{"subject": "x", "relation": "y", "obj": "z"}]
    js = '[{"subject": "Zeus", "relation": "domain", "object": "sky"}, ["Hera", "domain", "marriage"], "prose"]'
    got = K.extract("a.json", js)
    assert [f["subject"] for f in got["facts"]] == ["Zeus", "Hera"] and len(got["prose"]) == 1
    assert K.extract("a.json", "{nope")["error"]
    assert K.kind_of("a.pdf") is None and K.kind_of("Proof.lean") == "lean"


def test_preview_writes_nothing_and_reports_in_plain_words():
    titan = _titanos()
    titan.learn("Lisbon", "capital_of", "Coimbra", valid_from="1100-01-01", valid_to="1300-01-01")
    titan.learn("Acme", "based_in", "Porto", valid_from="2000-01-01")
    before = list(titan.facts)
    out = K.preview_items([{"name": "paste.md", "text": PASTE}], titanos=titan, lean_fn=lambda s: {})
    item = out["items"][0]
    assert titan.facts == before
    assert "held back 2 (not clear facts)" in item["status"]
    assert item["ready"] >= 1


def test_overlapping_fact_shows_as_conflict():
    titan = _titanos()
    titan.learn("Athens", "capital_of", "Sparta", valid_from="1800-01-01", valid_to="1900-01-01")
    out = K.preview_items([{"name": "p.txt", "text": "Athens | capital_of | Greece | 1834-01-01"}], titanos=titan)
    assert out["items"][0]["facts"][0]["action"] == "conflict"
    assert "1 conflict with an existing fact" in out["items"][0]["status"]


def test_lean_that_checks_becomes_a_candidate_and_failing_lean_does_not():
    src = "theorem two_eq : 1 + 1 = 2 := rfl\nlemma my.lem : True := trivial\n"
    ok = K.preview_items([{"name": "Proof.lean", "text": src}], lean_fn=lambda s: {"status": "CHECKED"})
    item = ok["items"][0]
    assert item["status"].startswith("Proof checks")
    assert [f["subject"] for f in item["facts"]] == ["two_eq", "my.lem"]
    bad = K.preview_items([{"name": "Proof.lean", "text": src}], lean_fn=lambda s: {"status": "FAILED", "line": 1})
    assert bad["items"][0]["status"] == "Proof doesn't check (line 1)" and bad["items"][0]["facts"] == []
    assert K.preview_items([{"name": "x.pdf", "text": ""}])["items"][0]["status"].startswith("Can't read")


def test_commit_goes_through_eat_and_keeps_bounds():
    titan = _titanos()
    out = K.commit_facts(
        [{"subject": "Athens", "relation": "capital_of", "obj": "Greece", "valid_from": "1834-01-01", "item": "paste"},
         {"subject": "sys:root", "relation": "is", "obj": "x"},
         {"nonsense": True}],
        titanos=titan,
    )
    assert out["saved"] == 1 and out["status"].startswith("Saved 1 fact")
    assert ("Athens", "capital_of", "Greece", "1834-01-01", None) in titan.facts
    assert out["held_back"] == 2


def test_knowledge_endpoints_are_admin_only(client, keys):  # noqa: F811
    body = {"items": [{"name": "p.txt", "text": "Kintsugi | origin | Japan"}]}
    assert client.post("/api/v1/knowledge/preview", json=body, headers={"X-API-Key": "user-key"}).status_code == 403
    commit = {"facts": [{"subject": "Kintsugi", "relation": "origin", "obj": "Japan"}], "confirm": True}
    assert client.post("/api/v1/knowledge/commit", json=commit, headers={"X-API-Key": "user-key"}).status_code == 403
    assert client.post("/api/v1/hermes/crawl", json={"urls": []}, headers={"X-API-Key": "user-key"}).status_code == 403
    ok = client.post("/api/v1/knowledge/preview", json=body,
                     headers={"X-API-Key": "user-key", **admin_headers("POST", "/knowledge/preview")})
    assert ok.status_code == 200, ok.text
    assert ok.json()["items"][0]["facts"][0]["subject"] == "Kintsugi"
    unconfirmed = client.post("/api/v1/knowledge/commit", json={**commit, "confirm": False}, headers={"X-API-Key": "ops-key"})
    assert unconfirmed.status_code == 400


def test_preview_flags_batch_conflicts_and_already_saved():
    titan = _titanos()
    titan.learn("Lisbon", "capital_of", "Portugal")
    text = ("Athens | capital_of | Ottoman Empire | 1458-01-01 | 1834-01-01\n"
            "Athens | capital_of | Sparta | 1500-01-01 | 1600-01-01\nLisbon | capital_of | Portugal\n")
    item = K.preview_items([{"name": "p.txt", "text": text}], titanos=titan)["items"][0]
    assert [f["action"] for f in item["facts"]] == ["conflict", "conflict", "abstain"]
    assert "2 conflicts with another fact you're adding" in item["status"] and "1 already saved" in item["status"]
    assert item["held_back"] == 0
