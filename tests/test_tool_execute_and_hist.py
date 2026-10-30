"""Production layer: tool execute + frame histogram."""
from __future__ import annotations

from resileos.answer.frame_telemetry import (
    frame_histogram,
    record_frame,
    reset_frame_histogram,
)
from resileos.answer.tool_execute import execute_tool


class _Fake:
    def ask_list(self, s, r, inverse=False):
        if s == "Zeus" and r == "domain":
            return ["sky"]
        return []

    def chain(self, subject, hops):
        class A:
            value = "sky"
            path = [(subject, hops[0], "sky")]
            reason = ""
        return A()


def test_histogram_record():
    reset_frame_histogram()
    record_frame("exact", "ANSWERED")
    record_frame("unresolved", "NONE_CHANNEL")
    h = frame_histogram()
    assert h["exact"] == 1
    assert h["none_channel"] == 1


def test_execute_ask_hit():
    out = execute_tool(
        "resileos_ask",
        {"subject": "Zeus", "relation": "domain"},
        titanos=_Fake(),
    )
    assert out["status"] == "ANSWERED"
    assert out["frame"] == "exact"
    assert out["rows"] == ["sky"]
    assert "Never invent" in out["instruction"] or "only from rows" in out["instruction"].lower() or "Answer only" in out["instruction"]


def test_execute_ask_miss():
    out = execute_tool(
        "resileos_ask",
        {"subject": "Noone", "relation": "domain"},
        titanos=_Fake(),
    )
    assert out["status"] == "NO_ROWS"
    assert out["rows"] == []


def test_execute_abstain():
    out = execute_tool("resileos_abstain", {"reason": "test"}, titanos=_Fake())
    assert out["status"] == "ABSTAINED"
    assert out["frame"] == "abstained"


def test_execute_missing_args():
    out = execute_tool("resileos_ask", {}, titanos=_Fake())
    assert out["status"] == "NONE_CHANNEL"
    assert out["frame"] == "unresolved"
