# Cascade address

The cascade address is belt → frame → residual, implemented in
`src/resileos/ui/cascade_address.py`. In this repo **belt** means only
the 5-mod Human Belt.

## Belt and cascade

The cascade is the ordered frames (3, 5, 9, 12). The outer frame stays
12. Global steps to 9. It does not jump to 12.

Two generators make the belt:

```
2_dyadic + 3_triadic = 5_belt
```

Dyadic is the black/white chroma. Triadic is the RBY chroma. Their sum
is the 5-mod belt, which is the 3-5 frame. The Human Belt is the gate
between global and local.

## Pins

The 5-pin is a construction on the ordered cascade, not a label. It sits
at the 5-frame. A residual packet carries a pin, and the pin selects the
scale.

| Pin        | Level | Frame | Scale      |
| ---------- | ----- | ----- | ---------- |
| individual | 0     | 5     | edge       |
| local      | 1     | 5     | hub        |
| global     | 2     | 9     | latent_hub |

`pin_address("local")` returns belt 5, frame 5, waist 36.
`pin_address("global")` returns frame 9. That is the packet address from a
node to a hub to the latent hub. An unknown pin raises `ValueError`.

When no residual token is given, the path uses the pin's scale, for
example `5/5/hub` for local and `5/9/latent_hub` for global.

## Waist and debt quantum

The waist (N=36) caps the factors.

- `cap_factor_count(n)` returns `max(0, min(int(n), 36))`. Counts above
  36 are clipped to 36, not rejected with an exception. Negative counts
  clip to 0.
- `clip_factors(items)` returns the leading 36 entries of a sequence.
  A longer sequence is truncated, not rejected.
- `within_waist(n)` is true only for counts in 0..36 inclusive. A
  caller that should refuse an over-waist set can use this predicate
  instead of clipping.

The debt quantum (ε = 1/64) floors residual energy. A packet whose
energy is strictly below 1/64 is not kept: no learn, no scar. Energy
equal to 1/64 is kept. `keep_packet(energy)` returns that decision
only. It does not call learn, does not write a scar, and does not
change any verify gate.

## Memory tiers

The persona store already has three tiers (PR #31): individual, hub,
and latent. Those names are reused, not redefined.

| Store tier  | Pin        |
| ----------- | ---------- |
| individual  | individual |
| hub         | local      |
| latent      | global     |

`pin_for_tier` and `tier_for_pin` perform that mapping. They do not
promote data. Data still moves up a tier only by explicit opt-in on
the persona store. One-step subject promotion is described in
[tier promotion](../320-titanos/tier-promotion.md).

## Orientation scales

Orientation scales are matrix control for the visual path. Each named
scale selects a frame and an orientation. This does not build images,
call learn, or write a scar.

The proportion is `resileos.substrate.suite_constants.PHI`, the same
φ already used by the oscillator, Titanos ingest (`φ^{-level}`), and
the inter-frame motion scale (`MAGNETIC_PHASE / PHI` in
`residual_frame.motion_scale`). At scale level L the address weight is
`φ^{-L}`. That existing motion formula is not changed.

| Scale          | Frame | Orientation | Scale level | φ weight |
| -------------- | ----- | ----------- | ----------- | -------- |
| edge           | 3     | edge        | 0           | φ^{0}    |
| sun_earth_moon | 5     | near triad  | 1           | φ^{-1}   |
| orion          | 9     | outer mark  | 2           | φ^{-2}   |
| north_star     | 12    | pole        | 3           | φ^{-3}   |

`orientation_scale("orion")` returns scale_level 2, frame 9, and
`proportion` equal to the shared `PHI`. It has no `belt` field.

The scale formerly drafted as `local` is named `edge` (frame 3) so it
does not clash with the `local` hub pin (frame 5). The individual pin's
selected scale is also called `edge`; that is the memory-scale name on
the pin, not this orientation-scale name.

`embed_frame(arr, scale="orion")` reads this control and sets the
cascade address to Human Belt 5 and the control's frame. The pixel
matrix is not changed. `suite_residual` still receives the original
`belt` argument, so `residual_bin` does not shift just because a
scale was named. With `scale` omitted or empty, `embed_frame` matches
its previous behavior, including the same dict keys.

## Where it is recorded

`ControlPacket` and `VideoPacket` have optional `pin` and `address`
fields. Both default to `None` and are copied into `to_dict`. They are
recorded fields only. The clip stage does not assign a pin on its own,
and the existing verify gates are unchanged. Studio, visual, and
persona paths still do not call learn or write the scar matrix through
this module. `encode_sequence` records `kept` from the 1/64 keep floor
without changing `TEMPORAL_SIGMA` or `ACCEPT_ENERGY`.

## Renames

| Draft name | Name in the repo | Reason |
| ---------- | ---------------- | ------ |
| `src/resileos/ui/five_pin.py` | `src/resileos/ui/cascade_address.py` | Pins live with cascade addressing, not in a parallel module |
| `address(pin)` | `pin_address(pin)` | Distinguishes the pin construction from `cascade_address` |
| `src/resileos/ui/belt_scale.py` | same `cascade_address.py` | One cascade-address module; "belt" is not a second idea |
| `matrix_control(scale)` | `orientation_scale(scale)` | Names the visual orientation control, not a second belt |
| `belt` on that control (scale index 0..3) | `scale_level` | **Belt** means only the 5-mod Human Belt |
| orientation scale `local` (frame 3) | `edge` | Does not clash with the `local` hub pin (frame 5) |
| `src/resileos/answer/cascade_learn.py` | `src/resileos/persona/promote.py` | Tier promotion belongs with the persona store, not answer |
| `docs/five-pin.md` / `docs/studio/belt-scale.md` | `docs/200-core/cascade-address.md` | One page for the cascade address |
| `docs/320-titanos/cascade-learn.md` | `docs/320-titanos/tier-promotion.md` | Matches the persona promotion helper |

No new top-level Kin was added. Cascade addressing is a path shape,
not a new figure. Promotion stays under the existing persona package.
