"""
Tests for the leCore HTTP client.

All transport is mocked; no real leCore instance is required.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.integration.lecore_client import (
    LeCoreClient, Capability, InvokeResult,
    LeCoreUnreachable, LeCoreError,
)


def _mock_response(status=200, json_data=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.text = str(json_data)[:200]
    return m


# ── health ──────────────────────────────────────────────────────────────
def test_health_returns_dict():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True, "name": "leCore"})
        client = LeCoreClient(url="http://x")
        assert client.health()["ok"] is True


def test_health_raises_on_non_200():
    with patch("requests.get") as g:
        g.return_value = _mock_response(500, {"error": "boom"})
        client = LeCoreClient(url="http://x")
        with pytest.raises(LeCoreError):
            client.health()


def test_health_raises_on_unreachable():
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("nope")):
        client = LeCoreClient(url="http://x")
        with pytest.raises(LeCoreUnreachable):
            client.health()


# ── capabilities ────────────────────────────────────────────────────────
def test_capabilities_parses_dict():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"capabilities": ["a", "b"]})
        client = LeCoreClient(url="http://x")
        assert client.capabilities() == ["a", "b"]


def test_capabilities_parses_bare_list():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, ["x", "y", "z"])
        client = LeCoreClient(url="http://x")
        assert client.capabilities() == ["x", "y", "z"]


# ── tools ───────────────────────────────────────────────────────────────
def test_tools_parses_wrapped():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"tools": [{"name": "fft"}]})
        client = LeCoreClient(url="http://x")
        assert client.tools() == [{"name": "fft"}]


# ── search ──────────────────────────────────────────────────────────────
def test_search_parses_dict_items():
    payload = {"results": [
        {"name": "compress_series", "description": "compress a float series",
         "score": 0.91},
        {"name": "fft", "description": "compute the FFT", "score": 0.72},
    ]}
    with patch("requests.post") as p:
        p.return_value = _mock_response(200, payload)
        client = LeCoreClient(url="http://x")
        caps = client.search("compress a float series")
        assert len(caps) == 2
        assert caps[0].name == "compress_series"
        assert caps[0].score == pytest.approx(0.91)
        # Request body shape
        assert p.call_args.kwargs["json"] == {"query": "compress a float series"}


def test_search_parses_bare_list():
    with patch("requests.post") as p:
        p.return_value = _mock_response(200, ["fft", "compress"])
        client = LeCoreClient(url="http://x")
        caps = client.search("anything")
        assert [c.name for c in caps] == ["fft", "compress"]


# ── invoke ──────────────────────────────────────────────────────────────
def test_invoke_returns_result():
    with patch("requests.post") as p:
        p.return_value = _mock_response(200, {"ok": True, "result": {"n": 3}})
        client = LeCoreClient(url="http://x")
        res = client.invoke("count", {"items": [1, 2, 3]})
        assert res.ok is True
        assert res.result == {"n": 3}
        assert p.call_args.kwargs["json"] == {
            "name": "count", "args": {"items": [1, 2, 3]}
        }


def test_invoke_soft_fails_on_unreachable():
    with patch("requests.post",
               side_effect=requests.exceptions.ConnectionError("nope")):
        client = LeCoreClient(url="http://x")
        res = client.invoke("anything")
        assert res.ok is False
        assert res.error is not None


def test_invoke_soft_fails_on_500():
    with patch("requests.post") as p:
        p.return_value = _mock_response(500, {"error": "bad"})
        client = LeCoreClient(url="http://x")
        res = client.invoke("anything")
        assert res.ok is False
        assert "500" in (res.error or "")


def test_invoke_wraps_bare_result():
    with patch("requests.post") as p:
        p.return_value = _mock_response(200, {"answer": 42})
        client = LeCoreClient(url="http://x")
        res = client.invoke("compute")
        assert res.ok is True
        assert res.result == {"answer": 42}


# ── auth ────────────────────────────────────────────────────────────────
def test_auth_header_present_when_token_set():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True})
        client = LeCoreClient(url="http://x", token="secret")
        client.health()
        assert g.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_no_auth_header_when_token_absent():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True})
        client = LeCoreClient(url="http://x", token=None)
        client.health()
        assertavailable "Authorization" not in g.call_args.kwargs["headers"]


# ── availability ────────────────────────────────────────────────────────
def test_is_available_true():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True})
        assert LeCoreClient(url="http://x").is_() is True


def test_is_available_false_on_unreachable():
    with patch("requests.get",
               side_effect=requests.exceptions.ConnectionError("nope")):
        assert LeCoreClient(url="http://x").is_available() is False
