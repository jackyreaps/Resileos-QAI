"""Tests for the pluggable answer backends (RES-327)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.answer import (
    AnswerContext,
    HostedBackend,
    LocalHFBackend,
    StructuredBackend,
    build_backend,
    humanize_relation,
    list_backends,
    select_backend,
)


def _ctx(
    rows=("sky",),
    inverse=False,
    question="What is Zeus's domain?",
    subject="Zeus",
    relation="domain",
):
    return AnswerContext(
        question=question,
        subject=subject,
        relation=relation,
        inverse=inverse,
        rows=tuple(rows),
    )


# ── helpers ────────────────────────────────────────────────────────────
def test_humanize_relation_plain():
    assert humanize_relation("domain") == "domain"


def test_humanize_relation_underscored():
    assert humanize_relation("parent_of") == "parent of"


# ── structured renderer ────────────────────────────────────────────────
def test_structured_single_forward():
    out = StructuredBackend().render(_ctx(rows=("sky",)))
    assert out == "Zeus's domain is sky."


def test_structured_single_inverse():
    out = StructuredBackend().render(
        _ctx(subject="Zeus", rows=("sky",), inverse=True)
    )
    assert out == "sky's domain is Zeus."


def test_structured_multi_two():
    out = StructuredBackend().render(_ctx(rows=("Ares", "Athena")))
    assert out == "Zeus's domain: Ares and Athena."


def test_structured_multi_three():
    out = StructuredBackend().render(
        _ctx(rows=("Ares", "Athena", "Apollo"))
    )
    assert out == "Zeus's domain: Ares, Athena, and Apollo."


def test_structured_multi_inverse():
    out = StructuredBackend().render(
        _ctx(subject="sky", rows=("Zeus", "Poseidon"), inverse=True)
    )
    assert out == (
        "Entities with domain pointing at sky: Zeus and Poseidon."
    )


def test_structured_empty_forward():
    out = StructuredBackend().render(_ctx(rows=()))
    assert "no record" in out.lower()
    assert "Zeus" in out


def test_structured_empty_inverse():
    out = StructuredBackend().render(
        _ctx(subject="sky", rows=(), inverse=True)
    )
    assert "no record" in out.lower()
    assert "sky" in out


def test_structured_always_available():
    assert StructuredBackend().available() is True


def test_structured_name():
    assert StructuredBackend().name == "structured"


# ── availability ───────────────────────────────────────────────────────
def test_local_hf_availability_is_bool():
    assert isinstance(LocalHFBackend().available(), bool)


def test_hosted_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("RESILEOS_ANSWER_API_KEY", raising=False)
    assert HostedBackend().available() is False


def test_hosted_available_with_key(monkeypatch):
    monkeypatch.setenv("RESILEOS_ANSWER_API_KEY", "sk-test")
    assert HostedBackend().available() is True


def test_hosted_reads_env(monkeypatch):
    monkeypatch.setenv("RESILEOS_ANSWER_API_KEY", "sk-x")
    monkeypatch.setenv("RESILEOS_ANSWER_API_MODEL", "my-model")
    monkeypatch.setenv(
        "RESILEOS_ANSWER_API_BASE", "https://example.test/v1/"
    )
    b = HostedBackend()
    assert b.api_key == "sk-x"
    assert b.model == "my-model"
    assert b.api_base == "https://example.test/v1"


# ── selection ──────────────────────────────────────────────────────────
def test_build_backend_known():
    assert build_backend("structured").name == "structured"
    assert build_backend("local_hf").name == "local_hf"
    assert build_backend("hosted").name == "hosted"


def test_build_backend_case_insensitive():
    assert build_backend("STRUCTURED").name == "structured"


def test_build_backend_unknown_raises():
    with pytest.raises(ValueError):
        build_backend("nope")


def test_select_backend_explicit_structured(monkeypatch):
    monkeypatch.setenv("RESILEOS_ANSWER_BACKEND", "structured")
    assert select_backend().name == "structured"


def test_select_backend_auto_returns_valid_name(monkeypatch):
    monkeypatch.setenv("RESILEOS_ANSWER_BACKEND", "auto")
    b = select_backend()
    assert b.name in ("structured", "local_hf", "hosted")


def test_select_backend_unknown_falls_back(monkeypatch):
    monkeypatch.setenv("RESILEOS_ANSWER_BACKEND", "definitely-not-a-real-name")
    b = select_backend()
    assert b.name in ("structured", "local_hf", "hosted")


def test_list_backends_shape():
    items = list_backends()
    names = {i["name"] for i in items}
    assert names == {"structured", "local_hf", "hosted"}
    assert all("available" in i for i in items)
    by_name = {i["name"]: i for i in items}
    assert by_name["structured"]["available"] is True
