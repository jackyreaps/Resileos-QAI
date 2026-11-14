"""The public site stays simple: one short nav, a plain chat, a step-by-step
Studio, and admin tools only under /admin (enforced on the server)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "landing" / "public"
FUNCTIONS = ROOT / "landing" / "functions"

NAV_PAGES = [
    "index.html",
    "how-it-works.html",
    "kin.html",
    "pricing.html",
    "credits.html",
    "login.html",
    "account.html",
    "studio.html",
    "admin/index.html",
    "admin/reports.html",
    "admin/knowledge.html",
    "admin/diagnostics.html",
]


def read(rel: str) -> str:
    return (PUBLIC / rel).read_text(encoding="utf-8")


def visible(html: str) -> str:
    """Markup a visitor can see: drop scripts, styles, and comments."""
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S)
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


@pytest.mark.parametrize("rel", NAV_PAGES)
def test_every_page_has_the_same_short_nav(rel):
    html = read(rel)
    menu = re.search(r'<div class="nav-links" id="nav-menu">(.*?)</div>', html, re.S)
    assert menu, rel
    links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', menu.group(1))
    assert [href for href, _ in links] == ["/chat", "/studio", "/pricing", "/login"], rel
    assert [text.strip() for _, text in links] == ["Chat", "Studio", "Pricing", "Sign in"], rel
    assert "/assets/nav.js" in html, rel
    assert 'href="/admin' not in menu.group(1), rel


def test_chat_uses_the_shared_nav():
    html = read("chat.html")
    assert "/assets/nav.js" in html
    assert "/assets/site-nav.js" not in html


def test_nav_script_adds_admin_only_from_the_session():
    js = read("assets/nav.js")
    assert "/api/session/me" in js
    assert "me.admin" in js
    assert '["/admin", "Admin"]' in js
    for label in ('"Chat"', '"Studio"', '"Pricing"', '"Account"', '"Sign in"'):
        assert label in js
    for gone in ("How it works", "Kin", "Home"):
        assert f'"{gone}"' not in js


def test_chat_is_one_column_with_one_composer():
    html = read("chat.html")
    view = visible(html)
    # One composer: attach anything, the tool choice is automatic.
    assert 'id="btn-attach"' in html and 'id="attach-menu"' in html
    assert 'id="file-input"' in html and "multiple" in html.split('id="file-input"')[1].split(">")[0]
    assert 'id="attach-row"' in html
    assert 'id="btn-tools-menu"' in html and 'id="tools-menu"' in html
    for label in ("Upload from this device", "Choose from my Files", "Options",
                  "Search the web", "Make a picture", "Make a short clip",
                  "Optional. I pick the right steps on my own."):
        assert label in view, label
    assert "${apiUrl()}/assist" in html
    for gone in ('id="more-menu"', 'id="btn-more"', 'id="tools-panel"', 'id="kin-panel"', 'id="studio-panel"',
                 'id="ui-panel"', 'id="ledger-panel"', 'id="companion-panel"', 'id="settings-panel"',
                 'id="settings-debug"', 'id="settings-hub"'):
        assert gone not in html, gone


@pytest.mark.parametrize(
    "term",
    ["ingest", "Ingest", "Titanos", "residual", "Residual", "scar", "Hades", "Eat ", "Kin cycle",
     "learning cycle", "Learning cycle", "verify", "Raw payload", "technical details", "commit", "legion"],
)
def test_chat_has_no_internal_terms_on_screen(term):
    assert term not in visible(read("chat.html")), term


def test_chat_tools_have_no_admin_endpoints():
    html = read("chat.html") + read("assets/chat-ui.js")
    for path in ("/studio/graphify", "/kin/cycle", "/kin/hades", "/eat/preview", "/hub/", "/tools/",
                 "/perceive/", "/aphrodite/' + encodeURIComponent(hubId()) + '/preference"):
        assert path not in html, path
    assert "'/tool '" not in read("assets/chat-ui.js")
    assert "window.runStudio" not in read("assets/chat-ui.js")


def test_chat_details_fold_is_only_for_debug():
    html = read("chat.html")
    assert "if (debugReplies() && notes.length) {" in html
    assert "if (!debugOn()) return;" in read("assets/chat-ui.js")


def test_studio_is_a_four_step_flow():
    html = read("studio.html")
    view = visible(html)
    for text in ("What do you want to make?", "Picture", "Short clip", "Describe it", "Start from my photos",
                 "Style", "Color", "Motion", "Length", "Make it", "Details"):
        assert text in view, text
    assert '<details class="details" id="result-details">' in html
    for jargon in ("Kuramoto", "Betti", "chroma", "residual", "Forge", "Hephaestus", "stage"):
        assert jargon not in view, jargon


def test_studio_never_fakes_a_result():
    js = read("assets/studio.js")
    assert '"/studio/forge/video"' in js
    assert '"/studio/video"' in js
    assert "UNAVAILABLE" in js
    assert "Nothing was made" in js
    assert "won't pretend" in js
    # The 32x32 local pattern isn't made from a prompt, so Studio never shows it as a result.
    assert "/generate/local" not in js
    # Metrics only appear inside the Details list.
    assert "Kuramoto" in js and "Betti" in js
    assert js.index("Kuramoto") > js.index("function fillDetails")


def test_admin_tabs_and_plain_language():
    for rel in ("admin/index.html", "admin/reports.html", "admin/knowledge.html", "admin/diagnostics.html"):
        html = read(rel)
        assert 'id="admin-tabs"' in html, rel
        assert "/assets/admin.js" in html, rel
    js = read("assets/admin.js")
    for tab in ('"Reports"', '"Knowledge"', '"Diagnostics"'):
        assert tab in js
    for plain in ("Add facts", "Drop files here", "Use from My files", "Check facts", "Check one fact (doesn't save)",
                  "See what's saved", "Run a learning cycle", "Go back to a checkpoint",
                  "Show technical details under chat replies"):
        assert plain in js, plain
    # Saving facts needs an explicit confirm, and every save still goes through the server's checks.
    assert 'call("POST", "/knowledge/preview", { items: batch })' in js
    assert 'window.confirm("Save " + facts.length' in js
    assert 'call("POST", "/knowledge/commit", { facts: facts, confirm: true })' in js
    assert "if (!account.admin)" in js


def test_admin_is_enforced_on_the_server():
    gate = (FUNCTIONS / "_admin.js").read_text(encoding="utf-8")
    auth = (FUNCTIONS / "_auth.js").read_text(encoding="utf-8")
    assert "publicApiAllowed(method, parts)" in auth
    assert "isAdminEmail(session.email, env)" in auth
    assert "body.admin = isAdminEmail(session.email, env);" in auth
    allow = gate.split("const PUBLIC_API", 1)[1].split("];", 1)[0]
    for admin_only in ("graphify", "kin", "eat", "hub", "tools", "perceive", "preference", "reset"):
        assert admin_only not in allow, admin_only
    middleware = (FUNCTIONS / "admin" / "_middleware.js").read_text(encoding="utf-8")
    assert "handleAdminPage" in middleware


def test_site_js_fetches_config_only_where_it_is_used():
    js = read("assets/site.js")
    assert "const needsConfig = document.querySelector(" in js
    assert "(needsConfig ? api(\"/api/config\") : Promise.resolve(null))" in js
    assert (ROOT / "landing" / "functions" / "api" / "config.js").exists()
