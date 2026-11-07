"""Tests for hub address attachment."""
from resileos.answer.hub_address import address_for_hub_subject


def test_address_kinds():
    u = address_for_hub_subject("user:1")
    w = address_for_hub_subject("world:materials")
    o = address_for_hub_subject("org:acme")
    assert u["kind"] == "user"
    assert w["kind"] == "world"
    assert o["kind"] == "org"
    assert u["address"]["residual_bin"]
