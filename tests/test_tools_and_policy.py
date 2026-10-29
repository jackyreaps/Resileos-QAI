"""Tier A: tool schemas and sector policy."""
from __future__ import annotations

from resileos.answer.policy import gbx_bypass_recurrent, prefer_child
from resileos.answer.tools_schema import (
    frame_index,
    list_tool_schemas,
    openai_tools,
)


def test_tool_schemas_nonempty():
    tools = list_tool_schemas()
    names = {t["name"] for t in tools}
    assert "resileos_ask" in names
    assert "resileos_chain" in names
    assert "resileos_abstain" in names
    assert "resileos_answer" in names


def test_openai_envelope():
    oai = openai_tools()
    assert all(x["type"] == "function" for x in oai)
    assert oai[0]["function"]["name"].startswith("resileos_")


def test_frame_index():
    idx = frame_index()
    assert idx["resileos_abstain"] == "abstain"
    assert idx["resileos_ask"] == "operational"


def test_prefer_child():
    assert prefer_child(sector="gbx_like") == "parent"
    assert prefer_child(sector="otx_like") == "zeus"
    assert prefer_child(sector="") == "zeus"


def test_gbx_bypass():
    assert gbx_bypass_recurrent("gbx_like") is True
    assert gbx_bypass_recurrent("otx_like") is False
