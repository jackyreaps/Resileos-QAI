# Five-pin cascade address

The 5-pin is a construction on the ordered cascade, not a label. It sits
at the 5-frame. A residual packet carries a pin, and the pin selects the
scale. This page records the framework as used in
`src/resileos/ui/five_pin.py`. The address is built with the existing
`cascade_address` helper (belt -> frame -> residual).

## Cascade and belt

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

Three scales sit on that belt. They are the pins, outward:

| Pin        | Level | Frame | Scale      |
| ---------- | ----- | ----- | ---------- |
| individual | 0     | 5     | edge       |
| local      | 1     | 5     | hub        |
| global     | 2     | 9     | latent_hub |

`address("local")` returns belt 5, frame 5, waist 36.
`address("global")` returns frame 9. That is the packet address from a
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
the persona store.

## Where it is recorded

`ControlPacket` and `VideoPacket` have optional `pin` and `address`
fields. Both default to `None` and are copied into `to_dict`. They are
recorded fields only. The clip stage does not assign a pin on its own,
and the existing verify gates are unchanged. Studio, visual, and
persona paths still do not call learn or write the scar matrix through
this module.

## Related

Visual-path matrix control is described in
[belt-scale](../studio/belt-scale.md). That page's `belt` field is a
scale index (0..3), not this 5-mod Human Belt. One-step outward
promotion of a verified, opted-in fact is described in
[cascade promotion](../320-titanos/cascade-learn.md).
