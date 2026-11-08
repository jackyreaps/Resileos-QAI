"""Tests for search, explain, and remember."""
from resileos.ui.explain_remember import explain, remember
from resileos.ui.search_flow import search


def test_search_hub_hit():
    def ask(s, r):
        return "sky" if s == "Zeus" else None

    out = search("zeus domain", ask=ask, subject="Zeus", relation="domain")
    assert out["hub_hit"] is True
    assert out["offer_save"] is False


def test_search_offers_save():
    out = search("what is a meson", ask=lambda s, r: None, subject="meson")
    assert out["hub_hit"] is False
    assert out["offer_save"] is True
    assert "duckduckgo" in out["web_url"]


def test_explain_and_remember():
    ex = explain("domain", ["sky"])
    assert ex["source"] == "hub"
    fact = remember("ada", "likes", "geometry")
    assert fact["subject"] == "user:ada"
