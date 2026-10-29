"""Tests for the framework-native gate encoder (RES-327 / gate-encoder)."""
from __future__ import annotations

import math

import pytest

from resileos.answer.native_encode import (
    GateSelection,
    encode_gate,
    encode_question,
)


ENTITIES = ["Zeus", "Athena", "Hera", "Apollo", "sky", "Olympus"]
RELATIONS = ["domain", "parent_of", "spouse_of", "symbol_of", "sibling_of"]


class TestEncodeGate:
    def test_forward_attribute_is_gbx(self):
        g = encode_gate(
            "What is Zeus's domain?",
            entities=ENTITIES,
            relations=RELATIONS,
        )
        assert g is not None
        assert g.subject == "Zeus"
        assert g.relation == "domain"
        assert g.inverse is False
        assert g.sector == "gbx_like"
        assert g.symbol_index == RELATIONS.index("domain")
        assert g.gate_capacity_bits == pytest.approx(math.log2(len(RELATIONS)))

    def test_inverse_parent_is_otx(self):
        g = encode_gate(
            "Who is the parent of Athena?",
            entities=ENTITIES,
            relations=RELATIONS,
        )
        assert g is not None
        assert g.subject == "Athena"
        assert g.relation == "parent_of"
        assert g.inverse is True
        assert g.sector == "otx_like"

    def test_domain_of_zeus_forward_gbx(self):
        g = encode_gate(
            "domain of Zeus",
            entities=ENTITIES,
            relations=RELATIONS,
        )
        assert g is not None
        assert g.subject == "Zeus"
        assert g.relation == "domain"
        assert g.inverse is False
        assert g.sector == "gbx_like"

    def test_bare_pair(self):
        g = encode_gate("Zeus domain", entities=ENTITIES, relations=RELATIONS)
        assert g is not None
        assert g.as_triple() == ("Zeus", "domain", False)

    def test_unresolved_returns_none(self):
        assert encode_gate("???", entities=ENTITIES, relations=RELATIONS) is None
        assert encode_gate("", entities=ENTITIES, relations=RELATIONS) is None
        assert encode_gate("gibberish with no structure", entities=ENTITIES, relations=RELATIONS) is None

    def test_empty_vocab_returns_none(self):
        assert encode_gate("Zeus domain", entities=[], relations=RELATIONS) is None
        assert encode_gate("Zeus domain", entities=ENTITIES, relations=[]) is None

    def test_encode_question_wrapper(self):
        t = encode_question("Zeus domain", entities=ENTITIES, relations=RELATIONS)
        assert t == ("Zeus", "domain", False)
        assert encode_question("???", entities=ENTITIES, relations=RELATIONS) is None

    def test_capacity_scales_with_alphabet(self):
        g4 = encode_gate("Zeus domain", entities=ENTITIES, relations=RELATIONS[:4])
        g5 = encode_gate("Zeus domain", entities=ENTITIES, relations=RELATIONS)
        assert g4 is not None and g5 is not None
        assert g4.gate_capacity_bits == pytest.approx(2.0)
        assert g5.gate_capacity_bits == pytest.approx(math.log2(5))

    def test_gate_selection_frozen(self):
        g = encode_gate("Zeus domain", entities=ENTITIES, relations=RELATIONS)
        assert isinstance(g, GateSelection)
        with pytest.raises(Exception):
            g.subject = "Hera"  # type: ignore[misc]
