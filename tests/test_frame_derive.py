"""Truth-frame derivation from sector × gate_state × status."""
from resileos.answer.policy import (
    FRAME_ABSTAINED,
    FRAME_EXACT,
    FRAME_RECONSTRUCTED,
    FRAME_UNRESOLVED,
    derive_frame,
    frame_to_tool_tag,
    prefer_child,
)


def test_none_channel():
    assert derive_frame(status="NONE_CHANNEL") == FRAME_UNRESOLVED


def test_abstained():
    assert derive_frame(status="ABSTAINED", gate_state="REPULSE") == FRAME_ABSTAINED


def test_gbx_answered_exact():
    assert derive_frame(sector="gbx_like", status="ANSWERED", n_rows=1) == FRAME_EXACT


def test_otx_reconstructed():
    assert derive_frame(sector="otx_like", status="ANSWERED", n_rows=1) == FRAME_RECONSTRUCTED


def test_multi_row_reconstructed():
    assert derive_frame(sector="gbx_like", status="ANSWERED", n_rows=3) == FRAME_RECONSTRUCTED


def test_capacity_routes_parent():
    assert prefer_child(sector="otx_like", gate_capacity_bits=0.5, capacity_floor=1.0) == "parent"
    assert prefer_child(sector="otx_like", gate_capacity_bits=3.0, capacity_floor=1.0) == "zeus"


def test_frame_to_tool_tag():
    assert frame_to_tool_tag(FRAME_EXACT) == "operational"
    assert frame_to_tool_tag(FRAME_ABSTAINED) == "abstain"
