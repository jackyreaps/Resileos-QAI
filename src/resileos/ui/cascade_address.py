"""Cascade address: Human Belt -> frame -> residual.

The belt in this module is only the 5-mod Human Belt: 2 dyadic
(black/white chroma) + 3 triadic (RBY chroma) = 5, the 3-5 frame.
It is the gate between global and local. No other field is named belt.

The cascade is the ordered frames (3, 5, 9, 12). The outer frame stays
12. Global steps to 9; it does not jump to 12.

Two constructions sit on that cascade:

- Pins, at the 5-frame, select a memory scale: individual (edge),
  local (hub), global (latent_hub). ``pin_address`` builds the packet
  address. The waist (N=36) caps factors. The debt quantum (ε = 1/64)
  floors residual energy; ``keep_packet`` is that floor only and does
  not call learn or write a scar.
- Orientation scales, for the visual path, select a frame and an
  orientation. ``orientation_scale`` returns that control. The
  proportion is ``suite_constants.PHI``, the same φ the oscillator,
  Titanos ingest, and ``motion_scale`` (MAGNETIC_PHASE / PHI) already
  use. A frame's address is φ^{-(frame-3)} (frame 3 = 1): it places
  content and orders levels, it is never a gain on color or detail,
  and the 1/64 floor never applies to it. ``waist_span`` (36/f: 12, 4,
  3; none at the 5-frame, which is orientation only) is the block size
  at that frame, a structural division, not a fan-out cap. The waist
  of 36 is the only total limit. The orientation
  scale formerly called ``local`` is named ``edge`` (frame 3) so it
  does not clash with the ``local`` hub pin.

This module never builds an image, never promotes a fact, and never
writes a scar. Persona-store tiers map onto pins as Individual →
individual, Hub → local, Latent → global, with no automatic promotion.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence, TypeVar

# Ordered cascade. The outer frame stays 12.
CASCADE_FRAMES: tuple[int, ...] = (3, 5, 9, 12)
OUTER_FRAME = 12

# Belt generators: dyadic (black/white chroma) + triadic (RBY chroma).
# BELT is the 5-mod Human Belt. Nothing else in this module is a belt.
DYADIC = 2
TRIADIC = 3
BELT = DYADIC + TRIADIC  # 5

# Waist caps the number of factors.
WAIST = 36

# Debt quantum. Same numeric value as ``resileos.packet.EPS``.
EPSILON = 1.0 / 64.0

# pin -> (level, frame, scale), outward on the Human Belt.
PINS: dict[str, dict[str, Any]] = {
    "individual": {"level": 0, "frame": 5, "scale": "edge"},
    "local": {"level": 1, "frame": 5, "scale": "hub"},
    "global": {"level": 2, "frame": 9, "scale": "latent_hub"},
}

# Existing persona-store tier names (not a new enum).
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

# Orientation scales for the visual path. scale_level is the index.
# ``edge`` is the former draft name ``local`` (frame 3).
ORIENTATION_SCALES: tuple[str, ...] = (
    "edge",
    "sun_earth_moon",
    "orion",
    "north_star",
)
_ORIENTATION_SPEC: dict[str, dict[str, Any]] = {
    "edge": {"frame": 3, "orientation": "edge"},
    "sun_earth_moon": {"frame": 5, "orientation": "near_triad"},
    "orion": {"frame": 9, "orientation": "outer_mark"},
    "north_star": {"frame": 12, "orientation": "pole"},
}

T = TypeVar("T")


def cascade_address(belt: int, frame: int, residual: str) -> dict[str, Any]:
    """Hierarchical address: Human Belt -> frame -> residual."""
    return {
        "belt": int(belt),
        "frame": int(frame),
        "residual": residual,
        "path": f"{belt}/{frame}/{residual}",
    }


def is_valid_address(addr: dict[str, Any]) -> bool:
    return (
        isinstance(addr.get("belt"), int)
        and isinstance(addr.get("frame"), int)
        and bool(addr.get("residual"))
    )


def _pin_spec(pin: str) -> dict[str, Any]:
    try:
        return PINS[pin]
    except KeyError:
        raise ValueError(f"unknown pin: {pin!r}") from None


def pin_address(pin: str, residual: str | None = None) -> dict[str, Any]:
    """Packet address for a pin on the cascade.

    ``pin_address("local")`` returns belt 5, frame 5, waist 36.
    ``pin_address("global")`` returns frame 9 (belt stays 5; frame is
    not 12). An unknown pin raises ``ValueError``.

    The path is ``belt/frame/residual``. When ``residual`` is omitted,
    the pin's scale is used (edge, hub, or latent_hub).
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
        "frame_control": frame_control(frame),
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


def phi_level_weight(level: int) -> float:
    """φ^{-level}, the existing outward address weight for a cascade level."""
    # Imported here to avoid a package cycle through substrate.__init__.
    from resileos.substrate.suite_constants import PHI

    return float(PHI ** (-int(level)))


# ── native 3/5/9/12 frame address ──────────────────────────────────────
# These are not powers of two, so they are not levels of a halving
# pyramid. In the suite each frame is a cascade level at the φ-power
# address. They share factors, so they are not one remainder code. They
# combine by orientation: the pentagram 3-5 is the figure, and 9 and 12
# are the outer frames it sits on. The waist N=36 is divisible by 3, 9
# and 12. It is not divisible by 5. The 5-frame is the orientation, not
# a divisor of the waist.


def phi_address(frame: int) -> float:
    """The suite address of a frame. φ^{-frame}, not a dyadic step."""
    if frame not in CASCADE_FRAMES:
        raise ValueError(frame)
    from resileos.substrate.suite_constants import PHI

    return float(PHI ** (-int(frame)))


def waist_span(frame: int) -> int | None:
    """Block size of the waist at this frame: 36 // frame, if it divides.

    3, 9, 12 divide 36 (12, 4, 3). 5 does not: None means orientation
    only, no span. This is a structural block division, a label; it is
    not a per-parent child cap. The waist (36) is the only total limit.
    """
    if WAIST % frame == 0:
        return WAIST // frame
    return None


def frame_control(frame: int) -> dict[str, Any]:
    """Control for a visual matrix at one cascade frame.

    address is the φ-power. span is the block size (36 // frame), a
    label, not a child cap; None when the frame is the orientation (5).
    """
    return {
        "frame": int(frame),
        "address": round(phi_address(frame), 6),
        "span": waist_span(frame),
        "orientation": frame == 5,
        "figure": "pentagram" if frame == 5 else "cascade",
        "note": "phi address; not a halving level",
    }


def frame_weight(frame: int) -> float:
    """A frame's φ address relative to frame 3: φ^{-(frame-3)}, so frame 3 is 1.

    This is an ADDRESS, not a gain. Use it only to rank and to order
    levels. Never multiply color, palette, or detail strength by it:
    outer frames place content, they don't dim it. Never compare it with
    the 1/64 floor either; that floor is for residual energy only.
    ``waist_span`` is the block size at a frame, not a cap; the waist of
    36 is the only total limit.
    """
    return phi_address(frame) / phi_address(CASCADE_FRAMES[0])


def orientation_scale(scale: str) -> dict[str, Any]:
    """Visual-path control for one orientation scale.

    ``orientation_scale("orion")`` returns scale_level 2, frame 9.
    There is no ``belt`` field here; belt is only the 5-mod Human
    Belt on a cascade path. ``proportion`` is the shared core
    ``PHI``. ``phi_weight`` is the frame's φ address relative to frame 3
    (``frame_weight``): an address for ordering, never a gain on color.
    ``frame_control`` carries the address, the block-size span (a label,
    not a cap), and whether the frame is the orientation (5). An
    unknown scale raises ``ValueError``.
    """
    try:
        index = ORIENTATION_SCALES.index(scale)
    except ValueError:
        raise ValueError(f"unknown orientation scale: {scale!r}") from None
    spec = _ORIENTATION_SPEC[scale]
    from resileos.substrate.suite_constants import PHI

    return {
        "scale": scale,
        "scale_level": index,
        "frame": int(spec["frame"]),
        "orientation": str(spec["orientation"]),
        "proportion": float(PHI),
        "phi_weight": frame_weight(int(spec["frame"])),
        "frame_control": frame_control(int(spec["frame"])),
    }
