"""Tests for the language tool."""
from resileos.ui.language_tool import detect_language, native_or_translate, translate


def test_detect_latin():
    d = detect_language("hello world")
    assert d["guess"] == "latin"
    assert "address" in d


def test_translate_without_provider_preserves():
    out = translate("hola", target="en")
    assert out["provider"] == "none"
    assert out["translated"] == "hola"


def test_prefer_native():
    out = native_or_translate("bonjour", prefer_native=True)
    assert out["native"] is True
    assert out["display"] == "bonjour"
