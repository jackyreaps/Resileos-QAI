"""Hermes crawl: native index first, prose abstains, only rigid facts reach Zeus."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from titanos import Titanos, TitanosConfig

import resileos.harness.separated as separated
from resileos.kin import hermes_crawl as hc
from resileos.kin.hades_notes import HadesNotes
from resileos.kin.legions import LegionError, _surfaces, invoke_legion, reset_legions


def _titanos():
    return Titanos(TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=6, seed=42, classical_conf=0.09, abstention_gate=0.035,
        sigma_E=10.0, sigma_k=3, E_sat=10.0, E_sigma=10.0, tau_sat=0.9, tau_low=0.1,
    ))


LD = {
    "@context": "https://schema.org", "@type": "Organization", "name": "Acme Labs",
    "foundingLocation": {"@type": "Place", "name": "Lisbon"}, "parentOrganization": "Acme Group",
    "startDate": "2019-03-01", "endDate": "2024-06-30", "dateModified": "2025-01-02",
    "interactionStatistic": {"userInteractionCount": 99999}, "likes": 5000,
}
PAGE = (
    "<html><head><title>Acme</title><script type='application/ld+json'>" + json.dumps(LD) + "</script></head>"
    "<body><p>Acme Labs is the most popular lab in Lisbon according to many readers. "
    "Everyone says Acme Labs is located in Porto these days, which is widely shared.</p></body></html>"
)
PROSE_ONLY = "<html><body><p>Acme Labs has a famous rooftop garden that people visit every year in spring.</p></body></html>"


def fake_fetch(pages):
    def fetch(url):
        if url in pages:
            return {"status": "SUCCESS", "content": pages[url], "url": url}
        return {"status": "BLOCKED", "content": ""}
    return fetch


@pytest.fixture
def index(tmp_path):
    idx = hc.NativeIndex(tmp_path / "index.jsonl")
    idx.add("https://acme.example/about", "Acme Labs research lab Lisbon founding", title="About Acme")
    idx.add("https://news.example/acme", "Acme Labs news Lisbon lab rooftop", title="Acme news")
    idx.add("https://other.example/x", "Unrelated page about gardening", title="Garden")
    return idx


def test_native_index_is_primary_and_fallback_is_off_by_default(index, monkeypatch):
    monkeypatch.delenv("RESILEOS_SEARCH_FALLBACK", raising=False)
    assert hc.fallback_from_env() is None
    out = hc.native_search("acme lisbon", index=index)
    assert [p["origin"] for p in out["packets"]] == ["native", "native"]
    assert out["fallback_used"] is None
    packet = out["packets"][0]
    assert set(packet) >= {"url", "domain", "retrieved_at", "tier", "snippet"}
    assert packet["domain"] == "acme.example" and packet["tier"] == "commercial"
    assert hc.native_search("zebra", index=index)["packets"] == []


def test_fallback_runs_only_when_the_index_is_empty_and_is_labelled(index, monkeypatch):
    class Fake:
        name = "fake"
        label = "Third-party fallback (fake)"
        calls = 0

        def search(self, query, max_results):
            Fake.calls += 1
            return [{"url": "https://fallback.example/a", "title": "A", "snippet": "zebra facts", "rank": 1}]

    hc.native_search("acme", index=index, fallback=Fake())
    assert Fake.calls == 0
    out = hc.native_search("zebra", index=index, fallback=Fake())
    assert Fake.calls == 1 and out["fallback_used"] == "fake"
    assert out["packets"][0]["origin"] == "fallback:fake"
    assert out["packets"][0]["origin_label"] == "Third-party fallback (fake)"
    monkeypatch.setenv("RESILEOS_SEARCH_FALLBACK", "duckduckgo")
    assert hc.fallback_from_env().name == "duckduckgo"


def test_tier_is_audit_only():
    assert hc.source_tier("https://data.example.gov/x") == "institutional"
    assert hc.source_tier("https://en.wikipedia.org/wiki/A") == "reference"
    assert hc.source_tier("not a url") == "unknown"


def test_prose_abstains_and_structured_quintuples_keep_provenance():
    cands = hc.extract_claims("https://acme.example/about", PAGE, retrieved_at="2026-11-13T00:00:00Z")
    structured = [c for c in cands if c["kind"] == "structured"]
    prose = [c for c in cands if c["kind"] == "prose"]
    assert prose and structured
    q = structured[0]
    assert q["claim"]["valid_from"] == "2019-03-01" and q["claim"]["valid_to"] == "2024-06-30"
    assert q["as_of"] == "2025-01-02" and q["source"] == "https://acme.example/about" and q["frame"] == 5
    out = hc.eat_bridge(prose)
    assert out["kept"] == 0
    assert {r["action"] for r in out["results"]} == {"abstain"}
    assert {r["reason"] for r in out["results"]} == {"unstructured_prose"}


def test_quintuple_frames():
    assert hc.Quintuple("a", "b", "c").frame == 3
    assert hc.Quintuple("a", "b", "c", "2020-01-01").frame == 5


def test_only_rigid_facts_reach_zeus_and_bounds_survive(tmp_path, monkeypatch):
    seen_rows = []
    real = separated.zeus_head

    def spy(proposal, reviewers, learn, **kw):
        seen_rows.extend(list(proposal.hub_rows) + [{"claim": c} for c in proposal.claims])
        return real(proposal, reviewers, learn, **kw)

    monkeypatch.setattr(separated, "zeus_head", spy)
    titan = _titanos()
    cands = hc.extract_claims("https://acme.example/about", PAGE)
    out = hc.eat_bridge(cands, titanos=titan, commit=True)
    assert out["committed"] >= 1
    assert seen_rows, "Zeus saw nothing"
    for row in seen_rows:
        if "claim" in row:
            assert len(row["claim"]) == 3 and row["claim"][0] == "Acme Labs"
        else:
            assert set(row) == {"subject", "relation", "obj"} and row["subject"] == "Acme Labs"
    # Temporal bounds survive Eat acceptance into Titanos.
    assert ("Acme Labs", "founding_location", "Lisbon", "2019-03-01", "2024-06-30") in titan.facts
    # Popularity never becomes a residual fact.
    flat = " ".join(str(part) for fact in titan.facts for part in fact).lower()
    assert "99999" not in flat and "5000" not in flat and "popular" not in flat and "commercial" not in flat
    # Prose about Porto abstained, so it was never written.
    assert "porto" not in flat


def test_noisy_wave_leaves_a_lesson_only_note(tmp_path):
    notes = HadesNotes(tmp_path / "notes.jsonl")
    cands = hc.extract_claims("https://x.example/", PROSE_ONLY)
    out = hc.eat_bridge(cands, notes=notes)
    assert out["noisy"] is True
    lines = notes.read()
    assert len(lines) == 1 and lines[0]["verified"] is False
    assert "Acme" not in json.dumps(lines[0])


def test_phi_rank_drops_under_epsilon_and_caps_at_waist():
    items = [{"url": f"u{i}", "relevance": 1.0, "wave": 1} for i in range(50)]
    items.append({"url": "tiny", "relevance": 0.001, "wave": 1})
    out = hc.phi_rank(items)
    assert len(out["kept"]) == 36 and out["dropped"] == 15
    assert all(k["weight"] >= 1 / 64 for k in out["kept"])
    deep = hc.phi_rank([{"url": "a", "relevance": 1, "wave": 1}, {"url": "b", "relevance": 1, "wave": 2}])
    assert deep["kept"][1]["weight"] == pytest.approx(1 / 1.6180339887, rel=1e-6)


def test_buzz_is_a_routing_hint_only():
    out = hc.pheme_buzz(["Acme Labs opened in Lisbon", "Acme Labs launch in Lisbon again"], ["old news"])
    assert out["is_fact"] is False and out["routing_hint"]
    assert out["pairs"] == [{"pair": ["Acme Labs", "Lisbon"], "count": 2}]


def test_run_waves_reports_plain_words_and_feeds_the_index(index, tmp_path):
    fetch = fake_fetch({"https://acme.example/about": PAGE, "https://news.example/acme": PROSE_ONLY})
    audit = tmp_path / "trace.jsonl"
    report = hc.run_waves("acme lisbon", index=index, depth=2, fetch_fn=fetch, audit_path=audit)
    assert report["searched"] >= 2 and report["followed"] == 2
    assert report["summary"].startswith(f"Searched {report['searched']} sources, followed 2 to the original pages, kept ")
    assert report["frames"][0] == 3
    trace = hc.crawl_trace(audit)
    assert trace["waves"] == 1 and "acme" not in audit.read_text()


def test_fanout_uses_the_guarded_fetch_by_default(monkeypatch):
    calls = []

    async def fake_guarded(url, **kw):
        calls.append(url)
        return {"status": "BLOCKED", "content": ""}

    import resileos.chat.assist as assist
    monkeypatch.setattr(assist, "guarded_fetch", fake_guarded)
    out = hc.ichnaea_fanout([{"url": "http://127.0.0.1/admin"}], max_follow=3)
    assert calls == ["http://127.0.0.1/admin"] and out["followed"] == [] and out["not_opened"] == 1


def test_no_crawl_legion_holds_learn_fn_or_writes(index, tmp_path):
    reset_legions()
    try:
        names = hc.register_hermes_crawl_legions(enable=True, index=index, fetch_fn=fake_fetch({}),
                                                 audit_path=str(tmp_path / "t.jsonl"))
        assert names == ["native_search", "pheme_buzz", "ichnaea_fanout", "crawl_trace"]
        for kin in ("hermes", "iris"):
            for fn in _surfaces.get(kin, {}).values():
                assert "learn_fn" not in fn.__code__.co_freevars
        with pytest.raises(LegionError):
            invoke_legion("hermes", "native_search", {"id": "p", "budget_remaining": {}}, query="acme", learn_fn=print)
        out = invoke_legion("hermes", "native_search", {"id": "p", "budget_remaining": {}}, query="acme")
        assert out["verified"] is False and out["gated_write"] is False and out["packets"]
    finally:
        reset_legions()
    assert hc.register_hermes_crawl_legions() == []


def test_chat_search_uses_our_index_and_never_the_outside_backend(tmp_path, monkeypatch):
    import asyncio

    import resileos.chat.assist as A
    import resileos.harness.legions.search as outside

    async def boom(*a, **k):
        raise AssertionError("third-party search must stay off by default")

    monkeypatch.setattr(outside, "web_search", boom)
    monkeypatch.delenv("RESILEOS_SEARCH_FALLBACK", raising=False)
    monkeypatch.setenv("RESILEOS_HERMES_INDEX", str(tmp_path / "idx.jsonl"))
    hc._SHARED.clear()
    idx = hc.shared_index()
    idx.add("https://acme.example/about", "Acme Labs research lab Lisbon", title="About Acme")
    idx.add("https://news.example/acme", "Acme Labs news Lisbon", title="Acme news")
    learned = []

    class Titan:
        def learn(self, *a, **k):
            learned.append(a)

    fetch = fake_fetch({"https://acme.example/about": PAGE, "https://news.example/acme": PROSE_ONLY})
    out = asyncio.run(A.run_assist(A.AssistBody(message="search for acme lisbon"), titanos=Titan(),
                                   fetch_fn=fetch, crawl_top=2))
    step = next(s for s in out["assist"]["trail"] if s["step"] == "search")
    assert step["label"] == "Searched 2 sources, followed 2 to the original pages, kept 2 facts"
    assert "not saved" in step["detail"]
    assert {f["obj"] for f in step["facts"]} == {"Lisbon", "Acme Group"}
    assert learned == []  # chat never writes memory
    empty = asyncio.run(A.run_assist(A.AssistBody(message="search for zebras"), titanos=Titan(), crawl_top=2))
    assert any(s["label"] == "Searched our index: nothing found" for s in empty["assist"]["trail"])
    hc._SHARED.clear()


def test_agent_loop_search_is_native_first(tmp_path, monkeypatch):
    import asyncio

    from resileos.answer import agent_loop

    monkeypatch.delenv("RESILEOS_SEARCH_FALLBACK", raising=False)
    monkeypatch.setenv("RESILEOS_HERMES_INDEX", str(tmp_path / "idx.jsonl"))
    hc._SHARED.clear()
    hc.shared_index().add("https://acme.example/about", "Acme Labs Lisbon", title="Acme")
    body = asyncio.run(agent_loop._maybe_search("acme"))
    assert body["search"]["results"][0]["url"] == "https://acme.example/about"
    hc._SHARED.clear()
