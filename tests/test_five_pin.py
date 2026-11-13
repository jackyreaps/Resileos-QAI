"""Five-pin cascade address on the 5-frame."""
import pytest

from resileos.harness.packet import ControlPacket, VideoPacket
from resileos.ui.cascade_address import cascade_address
from resileos.ui.five_pin import (
    BELT,
    CASCADE_FRAMES,
    DYADIC,
    EPSILON,
    OUTER_FRAME,
    TRIADIC,
    WAIST,
    address,
    cap_factor_count,
    clip_factors,
    keep_packet,
    pin_for_tier,
    tier_for_pin,
    within_waist,
)


def test_address_local_returns_belt_5_frame_5_waist_36():
    addr = address("local")
    assert addr["belt"] == 5
    assert addr["frame"] == 5
    assert addr["waist"] == 36
    assert addr["pin"] == "local"
    assert addr["level"] == 1
    assert addr["scale"] == "hub"
    assert addr["epsilon"] == 1 / 64


def test_address_global_returns_frame_9():
    addr = address("global")
    assert addr["frame"] == 9
    assert addr["belt"] == 5
    assert addr["pin"] == "global"
    assert addr["level"] == 2
    assert addr["scale"] == "latent_hub"
    assert addr["frame"] != OUTER_FRAME
    assert addr["frame"] != 12


def test_address_individual():
    addr = address("individual")
    assert addr["pin"] == "individual"
    assert addr["level"] == 0
    assert addr["belt"] == 5
    assert addr["frame"] == 5
    assert addr["scale"] == "edge"
    assert addr["waist"] == 36
    assert addr["epsilon"] == EPSILON


def test_unknown_pin_raises():
    with pytest.raises(ValueError, match="unknown pin"):
        address("hub")
    with pytest.raises(ValueError, match="unknown pin"):
        address("edge")
    with pytest.raises(ValueError, match="unknown pin"):
        address("")


def test_epsilon_floor_keeps_equality_and_drops_below():
    # Energy < 1/64 is not kept. Energy == 1/64 is kept.
    assert keep_packet(1 / 64) is True
    assert keep_packet(EPSILON) is True
    assert keep_packet(1 / 64 + 1e-18) is True
    assert keep_packet(1 / 32) is True
    assert keep_packet(1 / 64 - 1e-18) is False
    assert keep_packet(0.0) is False
    assert keep_packet(-1.0) is False


def test_waist_caps_factor_counts_and_sequences():
    assert WAIST == 36
    assert cap_factor_count(36) == 36
    assert cap_factor_count(37) == 36
    assert cap_factor_count(100) == 36
    assert cap_factor_count(0) == 0
    assert cap_factor_count(-3) == 0
    assert within_waist(36) is True
    assert within_waist(0) is True
    assert within_waist(37) is False
    assert within_waist(-1) is False
    factors = list(range(40))
    assert clip_factors(factors) == list(range(36))
    assert clip_factors(range(10)) == list(range(10))


def test_persona_store_tiers_map_to_pins():
    # Reuses persona-store tier names (individual, hub, latent). No promotion.
    assert pin_for_tier("individual") == "individual"
    assert pin_for_tier("hub") == "local"
    assert pin_for_tier("latent") == "global"
    assert tier_for_pin("individual") == "individual"
    assert tier_for_pin("local") == "hub"
    assert tier_for_pin("global") == "latent"
    assert address(pin_for_tier("hub"))["frame"] == 5
    assert address(pin_for_tier("latent"))["frame"] == 9
    with pytest.raises(ValueError, match="unknown persona tier"):
        pin_for_tier("edge")
    with pytest.raises(ValueError, match="unknown pin"):
        tier_for_pin("latent")


def test_address_uses_cascade_address_path():
    addr = address("local")
    expected = cascade_address(5, 5, "hub")
    assert addr["path"] == expected["path"]
    assert addr["residual"] == expected["residual"]
    custom = address("global", residual="packet-hash")
    assert custom["path"] == cascade_address(5, 9, "packet-hash")["path"]
    assert custom["scale"] == "latent_hub"


def test_belt_and_cascade_constants():
    assert DYADIC + TRIADIC == BELT == 5
    assert CASCADE_FRAMES == (3, 5, 9, 12)
    assert OUTER_FRAME == 12


def test_video_packet_pin_and_address_default_to_none():
    packet = VideoPacket(id="clip")
    assert packet.pin is None
    assert packet.address is None
    data = packet.to_dict()
    assert data["pin"] is None
    assert data["address"] is None
    # Recorded only: attaching an address does not mark the packet verified
    # and does not invent a learn or scar write.
    held = address("local")
    recorded = VideoPacket(id="clip-local", pin="local", address=held)
    assert recorded.verified is False
    assert recorded.scars == []
    assert recorded.to_dict()["pin"] == "local"
    assert recorded.to_dict()["address"]["frame"] == 5
    control = ControlPacket(id="plain")
    assert control.pin is None and control.address is None
    assert control.to_dict()["pin"] is None
