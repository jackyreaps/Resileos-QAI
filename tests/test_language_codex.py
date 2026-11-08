"""Tests for the condensed language codex."""
from resileos.ui.language_codex import codex, cycle, namespace, speak, summarise


def test_speak_and_summary():
    rows = [{"subject": "Zeus", "relation": "domain", "obj": "sky"}]
    assert speak(rows)["epistemic"] == "GROUNDED"
    assert "sky" in summarise(rows)


def test_codex_and_cycle():
    store = {}
    def q(s, r):
        return store.get((s, r))
    def learn(s, r, o):
        store[(s, r)] = o
    out = cycle(q, learn, kind="user", name="ada", relation="domain", obj="sky")
    assert out["codex"]["epistemic"] == "GROUNDED"
    assert namespace("guild", "builders") == "guild:builders"


def test_codex_with_kin():
    from resileos.kin.psyche import Psyche
    rows = [{"subject": "Zeus", "relation": "domain", "obj": "sky"}]
    out = codex(rows, psyche=Psyche("user:ada"))
    assert "kin" in out
    assert out["kin"]["judgment"]["modalities"] == 1
