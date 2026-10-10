"""
Tests for the leCore HTTP client.

These tests run against a mock server (no real leCore required). They
assert the client's request shapes and response parsing.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


def test_health():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True, "name": "leCore"})
        client = LeCoreClient(url="http://x")
        assert client.health()["ok"] is True


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
        # request body shape
        call = p.call_args
        assert call.kwargs["json"] == {"query": "compress a float series"}


def test_search_parses_bare_list():
    with patch("requests.post") as p:
        p.return_value = _mock_response(200, ["fft", "compress"])
        client = LeCoreClient(url="http://x")
        caps = client.search("anything")
        assert [c.name for c in caps] == ["fft", "compress"]


def test_invoke_returns_result():
    with patch("requests.post") as p:
        p.return_value = _mock_response(200, {"ok": True, "result": {"n": 3}})
        client = LeCoreClient(url="http://x")
        res = client.invoke("count", {"items": [1, 2, 3]})
        assert res.ok is True
        assert res.result == {"n": 3}
        call = p.call_args
        assert call.kwargs["json"] == {"name": "count", "args": {"items": [1, 2, 3]}}


def test_invoke_soft_fails_on_unreachable():
    import requests
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("nope")):
        client = LeCoreClient(url="http://x")
        res = client.invoke("anything")
        assert res.ok is False
        assert res.error is not None


def test_hard_fail_on_non_200():
    with patch("requests.get") as g:
        g.return_value = _mock_response(500, {"error": "boom"})
        client = LeCoreClient(url="http://x")
        with pytest.raises(LeCoreError):
            client.health()


def test_auth_header_present_when_token_set():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True})
        client = LeCoreClient(url="http://x", token="secret")
        client.health()
        call = g.call_args
        assert call.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_no_auth_header_when_token_absent():
    with patch("requests.get") as g:
        g.return_value = _mock_response(200, {"ok": True})
        client = LeCoreClient(url="http://x", token=None)
        client.health()
        call = g.call_args
        assert "Authorization" not in call.kwargs["headers"]
