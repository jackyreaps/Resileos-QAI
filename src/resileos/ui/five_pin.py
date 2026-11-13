"""Five-pin: a construction on the ordered cascade, sitting at the 5-frame.

This is not a label. It is the packet address from a node to a hub to
the latent hub. It uses ``cascade_address`` (belt -> frame -> residual)
rather than a second address shape.

Definitions (the cascade and 5-pin framework):

- The cascade is the ordered frames (3, 5, 9, 12). The outer frame
  stays 12. Global steps to 9; it does not jump to 12.
- Two generators make the belt: 2 dyadic (black/white chroma) +
  3 triadic (RBY chroma) = 5, the 5-mod belt, i.e. the 3-5 frame.
  The Human Belt is the gate between global and local.
- The 5-pin sits at the 5-frame. Three scales sit on that belt,
  outward:

    pin          level  frame  scale
    individual   0      5      edge
    local        1      5      hub
    global       2      9      latent_hub

- A residual packet carries a pin. The pin selects the scale.
- The waist (N=36) caps the factors. ``cap_factor_count`` and
  ``clip_factors`` clip to 36; they do not raise. ``within_waist``
  is the predicate a caller can use to refuse an over-waist set.
- The debt quantum (epsilon = 1/64) floors residual energy.
  ``keep_packet(energy)`` is False when energy < 1/64, and True
  when energy >= 1/64 (equality is kept). A packet that is not
  kept is not learned and does not write a scar. This helper only
  returns that decision; it does not call learn or touch the scar
  matrix.

Persona store tiers (``resileos.persona.store``, PR #31) map onto
pins as Individual -> individual, Hub -> local, Latent -> global.
This module reuses those existing tier name strings. It does not
redefine the tiers, and it does not promote data between them.
Data still moves up only by explicit opt-in on the store.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence, TypeVar

from resileos.ui.cascade_address import cascade_address

# Ordered cascade. The outer frame stays 12.
CASCADE_FRAMES: tuple[int, ...] = (3, 5, 9, 12)
OUTER_FRAME = 12

# Belt generators: dyadic (black/white chroma) + triadic (RBY chroma).
DYADIC = 2
TRIADIC = 3
BELT = DYADIC + TRIADIC  # 5, the 5-mod belt, the 3-5 frame

# Waist caps the number of factors.
WAIST = 36

# Debt quantum. Same numeric value as ``resileos.packet.EPS``.
EPSILON = 1.0 / 64.0

# pin -> (level, frame, scale), outward on the belt.
PINS: dict[str, dict[str, Any]] = {
    "individual": {"level": 0, "frame": 5, "scale": "edge"},
    "local": {"level": 1, "frame": 5, "scale": "hub"},
    "global": {"level": 2, "frame": 9, "scale": "latent_hub"},
}

# Existing persona-store tier names (not a new enum).
# Individual -> individual, Hub -> local, Latent -> global.
TIER_TO_PIN: Mapping[str, str] = {
    "individual": "individual",
    "hub": "local",
    "latent": "global",
}
PIN_TO_TIER: Mapping[str, str] = {
    "individual": "individual",
    "local": "hub",
    "global": "latent",
}

T = TypeVar("T")


def _pin_spec(pin: str) -> dict[str, Any]:
    try:
        return PINS[pin]
    except KeyError:
        raise ValueError(f"unknown pin: {pin!r}") from None


def address(pin: str, residual: str | None = None) -> dict[str, Any]:
    """Packet address for a pin on the cascade.

    ``address("local")`` returns belt 5, frame 5, waist 36.
    ``address("global")`` returns frame 9 (belt stays 5; frame is not 12).
    An unknown pin raises ``ValueError``.

    The cascade path is ``belt/frame/residual``. When ``residual`` is
    omitted, the pin's scale is used (edge, hub, or latent_hub).
    """
    spec = _pin_spec(pin)
    frame = int(spec["frame"])
    scale = str(spec["scale"])
    token = scale if residual is None else residual
    path = cascade_address(BELT, frame, token)
    return {
        "pin": pin,
        "level": int(spec["level"]),
        "belt": BELT,
        "frame": frame,
        "scale": scale,
        "waist": WAIST,
        "epsilon": EPSILON,
        "residual": path["residual"],
        "path": path["path"],
    }


def keep_packet(energy: float) -> bool:
    """Whether residual energy clears the debt-quantum floor.

    Energy strictly below 1/64 is not kept (no learn, no scar).
    Energy equal to 1/64 is kept. This function only returns a
    boolean; it does not call learn or write a scar.
    """
    return float(energy) >= EPSILON


def within_waist(count: int) -> bool:
    """True when a factor count is in 0..36 inclusive."""
    return 0 <= int(count) <= WAIST


def cap_factor_count(count: int) -> int:
    """Clip a factor count to the waist.

    Returns ``max(0, min(int(count), 36))``. Counts above 36 are
    clipped to 36; they are not rejected with an exception. Negative
    counts clip to 0. Use ``within_waist`` if a caller should refuse
    an over-waist count instead of clipping it.
    """
    return max(0, min(int(count), WAIST))


def clip_factors(factors: Iterable[T]) -> list[T]:
    """Return at most 36 factors, keeping the leading entries.

    A sequence longer than the waist is truncated. It is not rejected
    with an exception. Use ``within_waist(len(factors))`` to refuse an
    over-waist set instead of clipping it.
    """
    if isinstance(factors, Sequence) and not isinstance(factors, (str, bytes)):
        return list(factors[:WAIST])
    items: list[T] = []
    for item in factors:
        if len(items) >= WAIST:
            break
        items.append(item)
    return items


def pin_for_tier(tier: str) -> str:
    """Map a persona-store tier name to a pin.

    ``individual`` -> ``individual``, ``hub`` -> ``local``,
    ``latent`` -> ``global``. Unknown tiers raise ``ValueError``.
    This does not promote data between tiers.
    """
    try:
        return TIER_TO_PIN[tier]
    except KeyError:
        raise ValueError(f"unknown persona tier: {tier!r}") from None


def tier_for_pin(pin: str) -> str:
    """Map a pin back to the persona-store tier it addresses.

    ``individual`` -> ``individual``, ``local`` -> ``hub``,
    ``global`` -> ``latent``. Unknown pins raise ``ValueError``.
    This does not promote data between tiers.
    """
    _pin_spec(pin)
    return PIN_TO_TIER[pin]
